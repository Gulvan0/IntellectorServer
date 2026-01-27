from datetime import datetime

from src.config.models import SecretConfig
from src.game.models.offer import GameOfferEvent, OfferActionBroadcastedData
from src.game.methods.get import get_active_offers, get_ongoing_finite_game
from src.game.datatypes import OfferAction, OutcomeKind
from src.net.core import MutableState
from src.pubsub.models.channel import GameEventChannel
from src.pubsub.outgoing_event.update import OfferActionPerformed
from src.board.piece import PieceColor
from src.utils.async_orm_session import AsyncSession

import src.notification.methods as notification_methods


async def end_game(
    session: AsyncSession,
    state: MutableState,
    secret_config: SecretConfig,
    game_id: int,
    outcome: OutcomeKind,
    winner_color: PieceColor | None,
    ended_at: datetime | None = None
) -> None:  # TODO: Add (and sometimes validate) precalculated args: time reserves, last ply, ...
    # TODO: Add to outcome table
    # TODO: Add to time updates table (calculate that!)
    # TODO: Send game ended events (multiple channels)

    await notification_methods.delete_game_started_notifications(
        game_id=game_id,
        vk_token=secret_config.integrations.vk.token,
        session=session
    )

    if state.shutdown_activated and not get_ongoing_finite_game(session):
        raise KeyboardInterrupt


async def cancel_all_active_offers(session: AsyncSession, state: MutableState, game_id: int, ply_dt: datetime) -> None:
    for offer_event in await get_active_offers(session, game_id):
        cancel_event = GameOfferEvent(
            occurred_at=ply_dt,
            action=OfferAction.CANCEL,
            offer_kind=offer_event.offer_kind,
            offer_author=offer_event.offer_author,
            game_id=game_id
        )
        session.add(cancel_event)

        broadcasted_event = OfferActionPerformed(OfferActionBroadcastedData.cast(cancel_event), GameEventChannel(game_id=game_id))
        await state.ws_subscribers.broadcast(broadcasted_event)
    await session.commit()
