
from src.common.user_ref import UserReference
from src.game.dependencies.ws import any_user_dependencies, player_dependencies
from src.game.endpoint_sinks import add_time_sink, append_ply_sink
from src.game.exceptions import PlyInvalidException, TimeoutReachedException
from src.game.ws.offer import accept_draw, accept_takeback, cancel_offer, create_offer, decline_offer
from src.game.models.chat import GameChatMessageEvent
from src.game.models.incoming_ws import AddTimeIntentData, ChatMessageIntentData, OfferActionIntentData, PlyIntentData
from src.game.models.other import GameId
from src.pubsub.models.channel import GameEventChannel
from src.net.core import WebSocketWrapper
from src.net.incoming import WebSocketHandlerCollection
from src.net.sub_storage import SubscriberTag
from src.game.methods.cast import compose_state_refresh
from src.game.methods.update import end_game
from src.game.methods.get import (
    get_current_sip_and_ply_cnt,
    get_last_ply_event,
)
from src.pubsub.outgoing_event.refresh import GameRefresh
from src.pubsub.outgoing_event.update import NewChatMessage
from src.rules import Position
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind


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
            refresh_payload = await compose_state_refresh(
                session=deps.session,
                game_id=payload.game_id,
                game=deps.db_game,
                reason='invalid_move',
                include_spectator_messages=False
            )
            await ws.send_event(GameRefresh(refresh_payload))


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

        event = NewChatMessage(await db_event.to_broadcasted_data(deps.session), GameEventChannel(game_id=payload.game_id))
        tag_blacklist = set()
        if not deps.db_game.outcome and is_spectator:
            tag_blacklist = {SubscriberTag.PARTICIPATING_PLAYER}
        await ws.app.mutable_state.ws_subscribers.broadcast(event, tag_blacklist)


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
