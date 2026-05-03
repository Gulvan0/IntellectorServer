from typing import Any
from game.datatypes import OfferAction, OfferKind
from game.models.chat import GameChatMessageEvent
from game.models.offer import GameOfferEvent
from game.models.ply import GamePlyEvent
from game.models.rollback import GameRollbackEvent
from game.models.time_added import GameTimeAddedEvent
from net.core import MutableState
from net.sub_storage import SubscriberTag
from player.methods import resolve_player_refs
from pubsub.models.channel import GameEventChannel
from pubsub.outgoing_event.base import OutgoingEvent
from pubsub.outgoing_event.update import NewChatMessage, NewPly, OfferActionPerformed, Rollback, TimeAdded
from board.piece import PieceColor
from utils.async_orm_session import AsyncSession


async def append_event(
    session: AsyncSession,
    mutable_state: MutableState,
    event: GamePlyEvent | GameChatMessageEvent | GameOfferEvent | GameTimeAddedEvent,
    game_id: int,
    commit: bool = True
) -> None:
    session.add(event)

    target_channel = GameEventChannel(game_id=game_id)
    tag_blacklist = set()
    match event:
        case GamePlyEvent():
            ws_event: OutgoingEvent[Any, Any] = NewPly(event.to_broadcasted_data(), target_channel)
            tag_blacklist.add(SubscriberTag.WHITE_PLAYER if event.moving_color == PieceColor.WHITE else SubscriberTag.BLACK_PLAYER)
        case GameChatMessageEvent():
            resolved_refs = await resolve_player_refs({event.author_ref}, session)
            ws_event = NewChatMessage(event.to_broadcasted_data(resolved_refs), target_channel)
        case GameOfferEvent():
            ws_event = OfferActionPerformed(event.to_broadcasted_data(), target_channel)
        case GameTimeAddedEvent():
            ws_event = TimeAdded(event.to_broadcasted_data(), target_channel)

    if commit:
        await session.commit()

    await mutable_state.ws_subscribers.broadcast(ws_event, tag_blacklist=tag_blacklist)


async def append_offer_event(
    session: AsyncSession,
    mutable_state: MutableState,
    action: OfferAction,
    offer_kind: OfferKind,
    offer_author: PieceColor,
    game_id: int,
    commit: bool = True
) -> None:
    await append_event(
        session=session,
        mutable_state=mutable_state,
        event=GameOfferEvent(
            action=action,
            offer_kind=offer_kind,
            offer_author=offer_author,
            game_id=game_id
        ),
        game_id=game_id,
        commit=commit
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
        await session.refresh(event)

    ws_event = Rollback(event.to_broadcasted_data(updated_sip), GameEventChannel(game_id=game_id))
    await mutable_state.ws_subscribers.broadcast(ws_event)
