from src.game.models.chat import GameChatMessageEvent
from src.game.models.offer import GameOfferEvent
from src.game.models.ply import GamePlyEvent
from src.game.models.rollback import GameRollbackEvent
from src.game.models.time_added import GameTimeAddedEvent
from src.net.core import MutableState
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.pubsub.models import GameEventChannel
from src.utils.async_orm_session import AsyncSession


async def append_event(
    session: AsyncSession,
    mutable_state: MutableState,
    event: GamePlyEvent | GameChatMessageEvent | GameOfferEvent | GameTimeAddedEvent,
    game_id: int,
    commit: bool = True
) -> None:
    session.add(event)
    if commit:
        await session.commit()

    match event:
        case GamePlyEvent():
            ws_event = WebsocketOutgoingEventRegistry.NEW_PLY
        case GameChatMessageEvent():
            ws_event = WebsocketOutgoingEventRegistry.NEW_CHAT_MESSAGE
        case GameOfferEvent():
            ws_event = WebsocketOutgoingEventRegistry.OFFER_ACTION_PERFORMED
        case GameTimeAddedEvent():
            ws_event = WebsocketOutgoingEventRegistry.TIME_ADDED
        case GameRollbackEvent():
            ws_event = WebsocketOutgoingEventRegistry.ROLLBACK

    await mutable_state.ws_subscribers.broadcast(
        ws_event,
        event.to_broadcasted_data(),
        GameEventChannel(game_id=game_id)
    )


async def append_rollback_event(
    session: AsyncSession,
    mutable_state: MutableState,
    event: GameRollbackEvent,
    game_id: int,
    updated_sip: str,
    commit: bool = True
) -> None:
    session.add(event)
    if commit:
        await session.commit()

    await mutable_state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.ROLLBACK,
        event.to_broadcasted_data(updated_sip),
        GameEventChannel(game_id=game_id)
    )
