from datetime import UTC, datetime

from src.common.user_ref import UserReference
from src.game.exceptions import PlyInvalidException, TimeoutReachedException
from src.game.models.chat import ChatMessageBroadcastedData, GameChatMessageEvent
from src.game.models.incoming_ws import AddTimeIntentData, ChatMessageIntentData, OfferActionIntentData, PlyIntentData
from src.game.models.main import Game
from src.game.models.offer import GameOfferEvent, OfferActionBroadcastedData
from src.game.models.other import GameId
from src.game.models.ply import GamePlyEvent
from src.game.models.rollback import GameRollbackEvent
from src.game.models.time_added import GameTimeAddedEvent
from src.pubsub.models import GameEventChannel
from src.game.models.time_update import GameTimeUpdateReason
from src.net.core import WebSocketWrapper
from src.net.incoming import WebSocketHandlerCollection
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.net.sub_storage import SubscriberTag
from src.net.utils.ws_error import WebSocketException
from src.game.methods.cast import compose_state_refresh, construct_new_ply_time_update
from src.game.methods.update import cancel_all_active_offers, end_game
from src.game.methods.get import (
    get_ply_history,
    is_offer_active,
    get_initial_time,
    get_last_ply_event,
    get_latest_time_update,
    has_occured_thrice,
    is_stale,
)
from src.rules import DEFAULT_STARTING_SIP, HexCoordinates, PieceColor, Ply, Position, PositionFinalityGroup
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind
from src.utils.async_orm_session import AsyncSession


collection = WebSocketHandlerCollection()


def get_current_sip_and_ply_cnt(game: Game, last_ply_event: GamePlyEvent | None) -> tuple[str, int]:
    if last_ply_event:
        return last_ply_event.sip_after, last_ply_event.ply_index + 1

    return game.custom_starting_sip or DEFAULT_STARTING_SIP, 0


# TODO: Split into reusable parts, remove duplicate code
@collection.register(PlyIntentData)
async def ply(ws: WebSocketWrapper, client: UserReference | None, payload: PlyIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        game = await session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.external_uploader_ref:
            raise WebSocketException(f"Game {payload.game_id} is external; use REST endpoints instead")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        if client.reference == game.white_player_ref:
            client_color = PieceColor.WHITE
        elif client.reference == game.black_player_ref:
            client_color = PieceColor.BLACK
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        prev_ply_event = await get_last_ply_event(session, payload.game_id)
        prev_sip, new_ply_index = get_current_sip_and_ply_cnt(game, prev_ply_event)
        prev_position = Position.default_starting() if prev_sip == DEFAULT_STARTING_SIP else Position.from_sip(prev_sip)

        if prev_position.color_to_move != client_color:
            raise WebSocketException("It's not your turn!")

        from_coords = HexCoordinates(payload.from_i, payload.from_j)
        to_coords = HexCoordinates(payload.to_i, payload.to_j)
        ply = Ply(from_coords, to_coords, payload.morph_into)

        try:
            if not prev_position.is_ply_possible(ply):
                raise PlyInvalidException

            perform_ply_result = prev_position.perform_ply_without_validation(ply)
            new_sip = perform_ply_result.new_position.to_sip()
            if payload.sip_after and new_sip != payload.sip_after:
                raise PlyInvalidException
        except PlyInvalidException:
            await ws.send_event(
                WebsocketOutgoingEventRegistry.REFRESH_GAME,
                await compose_state_refresh(
                    session=session,
                    game_id=payload.game_id,
                    game=game,
                    reason='invalid_move',
                    include_spectator_messages=False
                ),
                channel=None
            )
            return

        ply_dt = datetime.now(UTC)

        try:
            new_time_update = await construct_new_ply_time_update(
                session,
                payload.game_id,
                ply_dt,
                new_ply_index,
                color_to_move=perform_ply_result.new_position.color_to_move,
                timeout_grace_ms=0
            )
        except TimeoutReachedException as e:
            await end_game(
                session,
                ws.app.mutable_state,
                ws.app.secret_config,
                payload.game_id,
                OutcomeKind.TIMEOUT,
                e.winner,
                e.reached_at
            )
            return

        await cancel_all_active_offers(session, ws.app.mutable_state, payload.game_id, ply_dt)

        ply_event = GamePlyEvent(
            occurred_at=ply_dt,
            ply_index=new_ply_index,
            from_i=ply.departure.i,
            from_j=ply.departure.j,
            to_i=ply.destination.i,
            to_j=ply.destination.j,
            morph_into=ply.morph_into,
            game_id=payload.game_id,
            kind=perform_ply_result.ply_kind,
            moving_color=prev_position.color_to_move,
            moved_piece=perform_ply_result.moving_piece.kind,
            target_piece=perform_ply_result.target_piece.kind if perform_ply_result.target_piece else None,
            sip_after=new_sip,
            time_update=new_time_update
        )
        if new_time_update:
            session.add(new_time_update)
        session.add(ply_event)
        await session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.NEW_PLY,
            ply_event.to_broadcasted_data(),
            GameEventChannel(game_id=payload.game_id)
        )

        match perform_ply_result.new_position.get_finality_group():
            case PositionFinalityGroup.FATUM:
                await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.FATUM, client_color, ply_dt)
                return
            case PositionFinalityGroup.BREAKTHROUGH:
                await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.BREAKTHROUGH, client_color, ply_dt)
                return

        if has_occured_thrice(session, payload.game_id, new_sip):
            await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.REPETITION, None, ply_dt)
            return

        if is_stale(session, payload.game_id, new_ply_index):
            await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.NO_PROGRESS, None, ply_dt)
            return


@collection.register(ChatMessageIntentData)
async def send_chat_message(ws: WebSocketWrapper, client: UserReference | None, payload: ChatMessageIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        game = session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.external_uploader_ref:
            raise WebSocketException(f"Game {payload.game_id} is external; use REST endpoints instead")

        is_spectator = game.outcome or client.reference not in (game.white_player_ref, game.black_player_ref)

        db_event = GameChatMessageEvent(
            author_ref=client.reference,
            text=payload.text[:500],
            game_id=payload.game_id,
            spectator=is_spectator
        )
        session.add(db_event)
        await session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            event=WebsocketOutgoingEventRegistry.NEW_CHAT_MESSAGE,
            payload=ChatMessageBroadcastedData.cast(db_event),
            channel=GameEventChannel(game_id=payload.game_id),
            tag_blacklist={SubscriberTag.PARTICIPATING_PLAYER} if not game.outcome and is_spectator else set()
        )


async def submit_offer_action(
    session: AsyncSession,
    ws: WebSocketWrapper,
    action: OfferAction,
    offer_kind: OfferKind,
    offer_author: PieceColor,
    game_id: int,
    commit: bool = True
) -> None:
    event = GameOfferEvent(
        action=action,
        offer_kind=offer_kind,
        offer_author=offer_author,
        game_id=game_id
    )
    session.add(event)
    if commit:
        await session.commit()

    await ws.app.mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OFFER_ACTION_PERFORMED,
        OfferActionBroadcastedData(
            action=action,
            offer_kind=offer_kind,
            offer_author=offer_author,
            game_id=game_id,
            occurred_at=event.occurred_at
        ),
        GameEventChannel(game_id=game_id)
    )


async def cancel_offer(
    session: AsyncSession,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.CANCEL, offer_kind, offer_author, game_id)


async def decline_offer(
    session: AsyncSession,
    ws: WebSocketWrapper,
    game_id: int,
    offer_kind: OfferKind,
    offer_author: PieceColor
) -> None:
    if not await is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.DECLINE, offer_kind, offer_author, game_id)


async def accept_draw(session: AsyncSession, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, skip_activity_check: bool) -> None:
    if not skip_activity_check and not await is_offer_active(session, game_id, OfferKind.DRAW, offer_author):
        raise WebSocketException("Offer is not active")

    await submit_offer_action(session, ws, OfferAction.ACCEPT, OfferKind.DRAW, offer_author, game_id)

    await end_game(session, ws.app.mutable_state, ws.app.secret_config, game_id, OutcomeKind.DRAW_AGREEMENT, None)


async def accept_takeback(session: AsyncSession, ws: WebSocketWrapper, game_id: int, offer_author: PieceColor, game: Game) -> None:
    if not await is_offer_active(session, game_id, OfferKind.TAKEBACK, offer_author):
        raise WebSocketException("Offer is not active")

    ply_events = await get_ply_history(session, game_id, reverse_order=True)
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

    for event in cancelled_ply_events:
        event.is_cancelled = True
    session.add_all(cancelled_ply_events)

    if await is_offer_active(session, game_id, OfferKind.TAKEBACK, offer_author.opposite()):
        await submit_offer_action(session, ws, OfferAction.CANCEL, OfferKind.TAKEBACK, offer_author.opposite(), game_id, commit=False)
    await submit_offer_action(session, ws, OfferAction.ACCEPT, OfferKind.TAKEBACK, offer_author, game_id, commit=False)

    rollback_dt = datetime.now(UTC)

    new_last_ply_event = next(ply_events, None)
    if new_last_ply_event:
        time_update = new_last_ply_event.time_update
        current_sip = new_last_ply_event.sip_after
    else:
        time_update = await get_initial_time(session, game_id)
        current_sip = game.custom_starting_sip or DEFAULT_STARTING_SIP

    if time_update:
        time_update = time_update.model_copy()
        time_update.updated_at = rollback_dt
        time_update.reason = GameTimeUpdateReason.ROLLBACK
        time_update.ticking_side = Position.color_to_move_from_sip(current_sip) if new_ply_cnt >= 2 else None
        session.add(time_update)

    rollback_event = GameRollbackEvent(
        occurred_at=rollback_dt,
        ply_cnt_before=ply_cnt,
        ply_cnt_after=new_ply_cnt,
        requested_by=offer_author,
        game_id=game_id,
        time_update=time_update
    )
    session.add(rollback_event)
    await session.commit()

    await ws.app.mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.ROLLBACK,
        rollback_event.to_broadcasted_data(current_sip),
        GameEventChannel(game_id=game_id)
    )


async def create_offer(
    session: AsyncSession,
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

    if await is_offer_active(session, game_id, offer_kind, offer_author):
        raise WebSocketException("Offer is already active")

    if offer_kind == OfferKind.DRAW and is_offer_active(session, game_id, offer_kind, offer_author.opposite()):
        await accept_draw(session, ws, game_id, offer_author.opposite(), skip_activity_check=True)
        return

    await submit_offer_action(session, ws, OfferAction.CREATE, offer_kind, offer_author, game_id)


@collection.register(OfferActionIntentData)
async def perform_offer_action(ws: WebSocketWrapper, client: UserReference | None, payload: OfferActionIntentData):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        game = await session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.external_uploader_ref:
            raise WebSocketException(f"Game {payload.game_id} is external; use REST endpoints instead")

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
                last_ply_event = await get_last_ply_event(session, payload.game_id)
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

    async with ws.app.get_db_session() as session:
        game = await session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.external_uploader_ref:
            raise WebSocketException(f"Game {payload.game_id} is external; use REST endpoints instead")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        latest_time_update = await get_latest_time_update(session, payload.game_id)

        if not latest_time_update:
            raise WebSocketException(f"Game {payload.game_id} is a correspondence game")

        addition_dt = datetime.now(UTC)

        secs_added = ws.app.main_config.rules.secs_added_manually
        ms_added = secs_added * 1000

        appended_time_update = latest_time_update.model_copy()
        appended_time_update.updated_at = addition_dt
        appended_time_update.reason = GameTimeUpdateReason.TIME_ADDED
        if client.reference == game.white_player_ref:
            receiver = PieceColor.BLACK
            appended_time_update.black_ms += ms_added
        elif client.reference == game.black_player_ref:
            receiver = PieceColor.WHITE
            appended_time_update.white_ms += ms_added
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        time_added_event = GameTimeAddedEvent(
            occurred_at=addition_dt,
            amount_seconds=secs_added,
            receiver=receiver,
            game_id=payload.game_id,
            time_update=appended_time_update
        )

        session.add(time_added_event)
        session.add(appended_time_update)
        await session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.TIME_ADDED,
            time_added_event.to_broadcasted_data(),
            GameEventChannel(game_id=payload.game_id)
        )


@collection.register(GameId)
async def resign(ws: WebSocketWrapper, client: UserReference | None, payload: GameId):
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        game = await session.get(Game, payload.game_id)
        if not game:
            raise WebSocketException(f"Game {payload.game_id} does not exist")

        if game.external_uploader_ref:
            raise WebSocketException(f"Game {payload.game_id} is external; use REST endpoints instead")

        if game.outcome:
            raise WebSocketException(f"Game {payload.game_id} has already ended")

        if client.reference == game.white_player_ref:
            winner = PieceColor.BLACK
        elif client.reference == game.black_player_ref:
            winner = PieceColor.WHITE
        else:
            raise WebSocketException(f"You are not the player in game {payload.game_id}")

        last_ply_event = await get_last_ply_event(session, payload.game_id)
        if not last_ply_event or last_ply_event.ply_index < 1:
            await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.ABORT, None)
        else:
            await end_game(session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.RESIGN, winner)
