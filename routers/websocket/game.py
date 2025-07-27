from datetime import UTC, datetime, timedelta
from sqlalchemy import update
from sqlmodel import Session, and_, col, or_, select, func, case
from models.channel import GamePublicEventChannel
from models.game import AddTimeIntentData, ChatMessageBroadcastedData, ChatMessageIntentData, Game, GameChatMessageEvent, GameChatMessageEventPublic, GameOfferEvent, GameOfferEventPublic, GameOutcomePublic, GamePlyEvent, GamePlyEventPublic, GameRollbackEvent, GameRollbackEventPublic, GameStateRefresh, GameTimeAddedEvent, GameTimeAddedEventPublic, InvalidPlyResponseData, OfferActionBroadcastedData, OfferActionIntentData, PlyBroadcastedData, PlyIntentData, RollbackBroadcastedData, TimeAddedBroadcastedData
from net.fastapi_wrapper import WebSocketWrapper
from net.incoming import WebSocketHandlerCollection
from net.outgoing import WebsocketOutgoingEventRegistry
from net.sub_storage import SubscriberTag
from net.util import WebSocketException
from routers.shared_methods.game import compose_state_refresh, end_game, get_active_offers, get_ply_cnt, get_ply_history, is_offer_active
from routers.shared_queries.game import get_last_ply_event
from rules import DEFAULT_STARTING_SIP, HexCoordinates, PieceColor, PieceKind, Ply, PlyKind, Position, PositionFinalityGroup
from utils.datatypes import OfferAction, OfferKind, OutcomeKind, UserReference
from utils.query import count_if


collection = WebSocketHandlerCollection()


class _PlyInvalidException(Exception):
    pass


def get_current_sip_and_ply_cnt(game: Game, last_ply_event: GamePlyEvent | None) -> tuple[str, int]:
    if last_ply_event:
        return last_ply_event.sip_after, last_ply_event.ply_index + 1

    return game.custom_starting_sip or DEFAULT_STARTING_SIP, 0


@collection.register(PlyIntentData)
async def ply(ws: WebSocketWrapper, client: UserReference | None, payload: PlyIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    public_broadcast_channel = GamePublicEventChannel(game_id=payload.game_id)

    with Session(ws.app.db_engine) as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        if client.reference == game.white_player_ref:
            client_color = PieceColor.WHITE
        elif client.reference == game.black_player_ref:
            client_color = PieceColor.BLACK
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        prev_ply_event = get_last_ply_event(session, payload.game_id)
        prev_sip, new_ply_index = get_current_sip_and_ply_cnt(game, prev_ply_event)
        prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else Position.from_sip(prev_sip)

        if prev_position.color_to_move != client_color:
            raise WebSocketException("It's not your turn!")

        from_coords = HexCoordinates(payload.from_i, payload.from_j)
        to_coords = HexCoordinates(payload.to_i, payload.to_j)
        ply = Ply(from_coords, to_coords, payload.morph_into)

        try:
            if not prev_position.is_ply_possible(ply):
                raise _PlyInvalidException

            perform_ply_result = prev_position.perform_ply_without_validation(ply)
            new_sip = perform_ply_result.new_position.to_sip()
            if payload.sip_after and new_sip != payload.sip_after:
                raise _PlyInvalidException
        except _PlyInvalidException:
            await ws.send_event(
                WebsocketOutgoingEventRegistry.REFRESH_GAME,
                compose_state_refresh(
                    session=session,
                    game_id=payload.game_id,
                    game=game,
                    reason='invalid_move',
                    include_spectator_messages=False
                ),
                channel=None
            )
            return

        # Doing that before adding a new move to ensure correct count
        same_position_occurences_cnt = session.exec(select(
            func.count(col(GamePlyEvent.id))
        ).where(
            GamePlyEvent.game_id == payload.game_id,
            not GamePlyEvent.is_cancelled,
            GamePlyEvent.sip_after == new_sip
        )).one()
        is_threefold = same_position_occurences_cnt >= 2

        ply_dt = datetime.now(UTC)
        ply_ts = int(ply_dt.timestamp() * 1000)

        color_to_move = prev_position.color_to_move
        color_to_wait = color_to_move.opposite()

        ms_after_new_ply: dict[PieceColor, int | None] = {color: None for color in PieceColor}
        if game.fischer_time_control:
            if prev_ply_event and prev_ply_event.ply_index >= 1:
                ms_after_prev_ply = prev_ply_event.get_time_remainders_dict()
                assert ms_after_prev_ply

                prev_ply_ts = int(prev_ply_event.occurred_at.timestamp() * 1000)
                ms_passed = ply_ts - prev_ply_ts

                if ms_passed >= ms_after_prev_ply[color_to_move]:
                    ended_at_ts = prev_ply_ts + ms_after_prev_ply[color_to_move]
                    ended_at_dt = datetime.fromtimestamp(ended_at_ts)
                    await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.TIMEOUT, color_to_wait, ended_at_dt)
                    return

                ms_after_new_ply[color_to_move] = ms_after_prev_ply[color_to_move] - ms_passed + game.fischer_time_control.increment_seconds * 1000
                ms_after_new_ply[color_to_wait] = ms_after_prev_ply[color_to_wait]
            else:
                ms_after_new_ply[color_to_move] = game.fischer_time_control.start_seconds * 1000
                ms_after_new_ply[color_to_wait] = game.fischer_time_control.start_seconds * 1000

        for offer_event in get_active_offers(session, payload.game_id):
            cancel_event = GameOfferEvent(
                occurred_at=ply_dt,
                action=OfferAction.CANCEL,
                offer_kind=offer_event.offer_kind,
                offer_author=offer_event.offer_author,
                game_id=payload.game_id
            )
            session.add(cancel_event)

            await ws.app.mutable_state.ws_subscribers.broadcast(
                WebsocketOutgoingEventRegistry.OFFER_ACTION_PERFORMED,
                OfferActionBroadcastedData.model_construct(**cancel_event.model_dump()),
                public_broadcast_channel
            )
        session.commit()

        ply_event = GamePlyEvent(
            occurred_at=ply_dt,
            ply_index=new_ply_index,
            white_ms_after_execution=ms_after_new_ply[PieceColor.WHITE],
            black_ms_after_execution=ms_after_new_ply[PieceColor.BLACK],
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            game_id=payload.game_id,
            kind=perform_ply_result.ply_kind,
            moving_color=color_to_move,
            moved_piece=perform_ply_result.moving_piece.kind,
            target_piece=perform_ply_result.target_piece.kind if perform_ply_result.target_piece else None,
            sip_after=new_sip,
        )
        session.add(ply_event)
        session.commit()

        match perform_ply_result.new_position.get_finality_group():
            case PositionFinalityGroup.FATUM:
                await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.FATUM, client_color, ply_dt)
                return
            case PositionFinalityGroup.BREAKTHROUGH:
                await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.BREAKTHROUGH, client_color, ply_dt)
                return

        if is_threefold:
            await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.REPETITION, None, ply_dt)
            return

        last_progressive_ply_index = session.exec(select(
            GamePlyEvent.ply_index
        ).where(
            GamePlyEvent.game_id == payload.game_id,
            not GamePlyEvent.is_cancelled,
            or_(
                and_(
                    GamePlyEvent.target_piece != None,
                    GamePlyEvent.kind != PlyKind.SWAP
                ),
                GamePlyEvent.moved_piece == PieceKind.PROGRESSOR
            )
        )).first()
        is_no_progress = new_ply_index - (last_progressive_ply_index or -1) >= 60

        if is_no_progress:
            await end_game(session, ws.app.mutable_state, payload.game_id, OutcomeKind.NO_PROGRESS, None, ply_dt)
            return

        await ws.app.mutable_state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.NEW_PLY,
            PlyBroadcastedData(
                occurred_at=ply_dt,
                white_ms_after_execution=ms_after_new_ply[PieceColor.WHITE],
                black_ms_after_execution=ms_after_new_ply[PieceColor.BLACK],
                from_i=ply.departure.i,
                from_j=ply.departure.j,
                to_i=ply.destination.i,
                to_j=ply.destination.j,
                morph_into=ply.morph_into,
                game_id=payload.game_id,
                sip_after=new_sip
            ),
            public_broadcast_channel
        )


@collection.register(ChatMessageIntentData)
async def send_chat_message(ws: WebSocketWrapper, client: UserReference | None, payload: ChatMessageIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    with Session(ws.app.db_engine) as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        is_spectator = game.outcome or client.reference not in (game.white_player_ref, game.black_player_ref)

        event_db = GameChatMessageEvent(
            author_ref=client.reference,
            text=payload.text[:500],
            game_id=payload.game_id,
            spectator=is_spectator
        )
        session.add(event_db)
        session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            event=WebsocketOutgoingEventRegistry.NEW_CHAT_MESSAGE,
            payload=ChatMessageBroadcastedData.model_construct(**event_db.model_dump()),
            channel=GamePublicEventChannel(game_id=payload.game_id),
            tag_blacklist={SubscriberTag.PARTICIPATING_PLAYER} if not game.outcome and is_spectator else set()
        )


async def submit_offer_action(
    session: Session,
    ws: WebSocketWrapper,
    action: OfferAction,
    offer_kind: OfferKind,
    offer_author: PieceColor,
    game_id: int
) -> None:
    event = GameOfferEvent(
        action=action,
        offer_kind=offer_kind,
        offer_author=offer_author,
        game_id=game_id
    )
    session.add(event)
    session.commit()

    await ws.app.mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OFFER_ACTION_PERFORMED,
        OfferActionBroadcastedData(
            action=action,
            offer_kind=offer_kind,
            offer_author=offer_author,
            game_id=game_id,
            occurred_at=event.occurred_at
        ),
        GamePublicEventChannel(game_id=game_id)
    )


async def cancel_offer(
    session: Session,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.CANCEL, offer_kind, offer_author, game_id)


async def decline_offer(
    session: Session,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.DECLINE, offer_kind, offer_author, game_id)


async def accept_draw(session: Session, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, skip_activity_check: bool) -> None:
    if not skip_activity_check and not is_offer_active(session, game_id, OfferKind.DRAW, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.ACCEPT, OfferKind.DRAW, offer_author, game_id)

    await end_game(session, ws.app.mutable_state, game_id, OutcomeKind.DRAW_AGREEMENT, None)


async def accept_takeback(session: Session, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, game: Game) -> None:
    if not is_offer_active(session, game_id, OfferKind.TAKEBACK, offer_author):
        raise WebSocketException("Offer is not active")

    ply_events = get_ply_history(session, game_id, reverse_order=True)
    last_ply_event = next(ply_events, None)
    if not last_ply_event:
        await submit_offer_action(session, ws, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author, game_id)
        return

    color_to_move = Position.color_to_move_from_sip(last_ply_event.sip_after)
    ply_cnt = last_ply_event.ply_index + 1

    if offer_author == color_to_move:
        one_more_cancelled_ply_event = next(ply_events, None)
        if not one_more_cancelled_ply_event:
            await submit_offer_action(session, ws, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author, game_id)
            return

        new_ply_cnt = ply_cnt - 2
        cancelled_ply_events = [last_ply_event, one_more_cancelled_ply_event]
    else:
        new_ply_cnt = ply_cnt - 1
        cancelled_ply_events = [last_ply_event]

    if is_offer_active(session, game_id, OfferKind.TAKEBACK, offer_author.opposite()):
        await submit_offer_action(session, ws, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author.opposite(), game_id)
    await submit_offer_action(session, ws, OfferAction.ACCEPT, OfferKind.TAKEBACK, offer_author, game_id)

    new_last_ply_event = next(ply_events, None)
    if new_last_ply_event:
        white_ms = new_last_ply_event.white_ms_after_execution
        black_ms = new_last_ply_event.black_ms_after_execution
        last_ply_ts = new_last_ply_event.occurred_at
        current_sip = new_last_ply_event.sip_after
    else:
        if game.fischer_time_control:
            white_ms = game.fischer_time_control.start_seconds * 1000
            black_ms = game.fischer_time_control.start_seconds * 1000
        else:
            white_ms = None
            black_ms = None
        last_ply_ts = None
        current_sip = game.custom_starting_sip or DEFAULT_STARTING_SIP

    for event in cancelled_ply_events:
        event.is_cancelled = True
    session.add_all(cancelled_ply_events)
    session.commit()

    await ws.app.mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.ROLLBACK,
        RollbackBroadcastedData(
            game_id=game_id,
            updated_white_ms_after_last_ply=white_ms,
            updated_black_ms_after_last_ply=black_ms,
            updated_last_ply_timestamp=last_ply_ts,
            updated_sip=current_sip,
            updated_ply_cnt=new_ply_cnt
        ),
        GamePublicEventChannel(game_id=game_id)
    )


async def create_offer(
    session: Session,
    ws: WebSocketWrapper,
    game_id: int,
    color_to_move: PieceColor,
    ply_cnt: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if offer_kind == OfferKind.DRAW:
        if ply_cnt < 2:
            raise WebSocketException("Draw cannot be offered during the first two moves of the game")
    else:
        ply_cnt_threshold = 1 if color_to_move == PieceColor.WHITE else 2
        if ply_cnt < ply_cnt_threshold:
            raise WebSocketException("Cannot ask for a takeback before your first move")

    if is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is already active")

    if offer_kind == OfferKind.DRAW and is_offer_active(session, game_id, offer_kind, offer_author.opposite()):
        await accept_draw(session, ws, game_id, offer_author.opposite(), skip_activity_check=True)
        return

    await submit_offer_action(session, ws, OfferAction.CREATE, offer_kind, offer_author, game_id)


@collection.register(OfferActionIntentData)
async def perform_offer_action(ws: WebSocketWrapper, client: UserReference | None, payload: OfferActionIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    with Session(ws.app.db_engine) as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        if client.reference == game.white_player_ref:
            client_color = PieceColor.WHITE
        elif client.reference == game.black_player_ref:
            client_color = PieceColor.BLACK
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        match payload.action_kind:
            case OfferAction.CREATE:
                last_ply_event = get_last_ply_event(session, payload.game_id)
                current_sip, ply_cnt = get_current_sip_and_ply_cnt(game, last_ply_event)
                await create_offer(session, ws, payload.game_id, Position.color_to_move_from_sip(current_sip), ply_cnt, payload.offer_kind, client_color)
            case OfferAction.CANCEL:
                await cancel_offer(session, ws, payload.game_id, payload.offer_kind, client_color)
            case OfferAction.DECLINE:
                await decline_offer(session, ws, payload.game_id, payload.offer_kind, client_color.opposite())
            case OfferAction.ACCEPT:
                if payload.offer_kind == OfferKind.DRAW:
                    await accept_draw(session, ws, payload.game_id, client_color.opposite(), skip_activity_check=False)
                else:
                    await accept_takeback(session, ws, payload.game_id, client_color.opposite(), game)


@collection.register(AddTimeIntentData)
async def add_time(ws: WebSocketWrapper, client: UserReference | None, payload: AddTimeIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    with Session(ws.app.db_engine) as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        last_ply_event = get_last_ply_event(session, payload.game_id)
        if not last_ply_event:
            raise WebSocketException("Time may only be added after the first move has been made")

        if not last_ply_event.white_ms_after_execution or not last_ply_event.black_ms_after_execution:
            raise WebSocketException(f"Game {payload.game_id} is a correspondence game")

        secs_added = ws.app.main_config.rules.secs_added_manually
        ms_added = secs_added * 1000
        if client.reference == game.white_player_ref:
            receiver = PieceColor.BLACK
            updated_receiver_ms_at_ply_start = last_ply_event.black_ms_after_execution + ms_added
            last_ply_event.black_ms_after_execution = updated_receiver_ms_at_ply_start
        elif client.reference == game.black_player_ref:
            receiver = PieceColor.WHITE
            updated_receiver_ms_at_ply_start = last_ply_event.white_ms_after_execution + ms_added
            last_ply_event.white_ms_after_execution = updated_receiver_ms_at_ply_start
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        time_added_event = GameTimeAddedEvent(
            amount_seconds=secs_added,
            receiver=receiver,
            game_id=payload.game_id
        )

        session.add(time_added_event)
        session.add(last_ply_event)
        session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.TIME_ADDED,
            TimeAddedBroadcastedData(
                occurred_at=time_added_event.occurred_at,
                amount_seconds=secs_added,
                receiver=receiver,
                game_id=payload.game_id,
                updated_receiver_ms_at_ply_start=updated_receiver_ms_at_ply_start
            ),
            GamePublicEventChannel(game_id=payload.game_id)
        )


# TODO: Bot game handlers (moves, offers, smth else?)
