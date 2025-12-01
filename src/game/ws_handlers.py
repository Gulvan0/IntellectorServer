from datetime import UTC, datetime

from src.common.user_ref import UserReference
from src.game.dependencies.ws import any_user_dependencies, player_dependencies
from src.game.endpoint_sinks import add_time_sink, append_ply_sink
from src.game.exceptions import PlyInvalidException, TimeoutReachedException
from src.game.models.chat import ChatMessageBroadcastedData, GameChatMessageEvent
from src.game.models.incoming_ws import AddTimeIntentData, ChatMessageIntentData, OfferActionIntentData, PlyIntentData
from src.game.models.main import Game
from src.game.models.offer import GameOfferEvent, OfferActionBroadcastedData
from src.game.models.other import GameId
from src.game.models.rollback import GameRollbackEvent
from src.pubsub.models import GameEventChannel
from src.game.models.time_update import GameTimeUpdateReason
from src.net.core import WebSocketWrapper
from src.net.incoming import WebSocketHandlerCollection
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.net.sub_storage import SubscriberTag
from src.net.utils.ws_error import WebSocketException
from src.game.methods.cast import compose_state_refresh
from src.game.methods.update import end_game
from src.game.methods.get import (
    get_current_sip_and_ply_cnt,
    get_ply_history,
    is_offer_active,
    get_initial_time,
    get_last_ply_event,
)
from src.rules import DEFAULT_STARTING_SIP, PieceColor, Position
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind
from src.utils.async_orm_session import AsyncSession


collection = WebSocketHandlerCollection()


@collection.register(PlyIntentData)
async def ply(ws: WebSocketWrapper, client: UserReference | None, payload: PlyIntentData):
    async with player_dependencies(ws, client, payload.game_id, ended=False) as deps:
        try:
            await append_ply_sink(
                deps.session,
                ws.app.mutable_state,
                ws.app.secret_config,
                payload,
                deps.db_game,
                None,
                deps.client_color
            )
        except TimeoutReachedException as e:
            await end_game(
                deps.session,
                ws.app.mutable_state,
                ws.app.secret_config,
                payload.game_id,
                OutcomeKind.TIMEOUT,
                e.winner,
                e.reached_at
            )
        except PlyInvalidException:
            await ws.send_event(
                WebsocketOutgoingEventRegistry.REFRESH_GAME,
                await compose_state_refresh(
                    session=deps.session,
                    game_id=payload.game_id,
                    game=deps.db_game,
                    reason='invalid_move',
                    include_spectator_messages=False
                ),
                channel=None
            )


@collection.register(ChatMessageIntentData)
async def send_chat_message(ws: WebSocketWrapper, client: UserReference | None, payload: ChatMessageIntentData):
    async with any_user_dependencies(ws, client, payload.game_id, ended=False) as deps:
        is_spectator = deps.db_game.outcome or deps.client.reference not in (deps.db_game.white_player_ref, deps.db_game.black_player_ref)

        db_event = GameChatMessageEvent(
            author_ref=deps.client.reference,
            text=payload.text[:500],
            game_id=payload.game_id,
            spectator=is_spectator
        )
        deps.session.add(db_event)
        await deps.session.commit()

        await ws.app.mutable_state.ws_subscribers.broadcast(
            event=WebsocketOutgoingEventRegistry.NEW_CHAT_MESSAGE,
            payload=ChatMessageBroadcastedData.cast(db_event),
            channel=GameEventChannel(game_id=payload.game_id),
            tag_blacklist={SubscriberTag.PARTICIPATING_PLAYER} if not deps.db_game.outcome and is_spectator else set()
        )


# TODO: Move this and any other non-endpoint function from this module to `methods`
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


# TODO: Use sink (offer action submission somehow needs to be fitted in-between, has to be thought about)
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
    async with player_dependencies(ws, client, payload.game_id, ended=False) as deps:
        match payload.action_kind:
            case OfferAction.CREATE:
                last_ply_event = await get_last_ply_event(deps.session, payload.game_id)
                current_sip, ply_cnt = get_current_sip_and_ply_cnt(deps.db_game, last_ply_event)
                await create_offer(deps.session, ws, payload.game_id, Position.color_to_move_from_sip(current_sip), ply_cnt, payload.offer_kind, deps.client_color)
            case OfferAction.CANCEL:
                await cancel_offer(deps.session, ws, payload.game_id, payload.offer_kind, deps.client_color)
            case OfferAction.DECLINE:
                await decline_offer(deps.session, ws, payload.game_id, payload.offer_kind, deps.client_color.opposite())
            case OfferAction.ACCEPT:
                if payload.offer_kind == OfferKind.DRAW:
                    await accept_draw(deps.session, ws, payload.game_id, deps.client_color.opposite(), skip_activity_check=False)
                else:
                    await accept_takeback(deps.session, ws, payload.game_id, deps.client_color.opposite(), deps.db_game)


@collection.register(AddTimeIntentData)
async def add_time(ws: WebSocketWrapper, client: UserReference | None, payload: AddTimeIntentData):
    async with player_dependencies(ws, client, payload.game_id, ended=False) as deps:
        await add_time_sink(deps.session, ws.app.main_config, ws.app.mutable_state, payload, deps.client_color.opposite())


@collection.register(GameId)
async def resign(ws: WebSocketWrapper, client: UserReference | None, payload: GameId):
    async with player_dependencies(ws, client, payload.game_id, ended=False) as deps:
        last_ply_event = await get_last_ply_event(deps.session, payload.game_id)
        if not last_ply_event or last_ply_event.ply_index < 1:
            await end_game(deps.session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.ABORT, None)
        else:
            await end_game(deps.session, ws.app.mutable_state, ws.app.secret_config, payload.game_id, OutcomeKind.RESIGN, deps.client_color.opposite())
