from datetime import UTC, datetime, timedelta
from sqlmodel import Session

from src.config.models import SecretConfig
from src.game.models.main import Game
from src.game.models.offer import GameOfferEvent, OfferActionBroadcastedData
from src.game.models.outcome import GameOutcome
from src.game.methods.get import get_active_offers, get_latest_time_update, get_ongoing_finite_game
from src.game.datatypes import OfferAction, OutcomeKind
from src.net.core import MutableState
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.pubsub.models import GameEventChannel
from src.rules import PieceColor
from src.utils.cast import model_cast

import time
import src.notification.methods as notification_methods


async def end_game(
    session: Session,
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

    notification_methods.delete_game_started_notifications(
        game_id=game_id,
        vk_token=secret_config.integrations.vk.token,
        session=session
    )

    if state.shutdown_activated and not get_ongoing_finite_game(session):
        raise KeyboardInterrupt

    state.game_timeout_not_earlier_than.pop(game_id, None)


async def check_timeout(
    *,
    session: Session,
    state: MutableState,
    secret_config: SecretConfig,
    game_id: int,
    outcome_abscence_checked: bool = False,
) -> bool:
    threshold = state.game_timeout_not_earlier_than.get(game_id)
    if not threshold or threshold > time.time():
        return False

    if not outcome_abscence_checked and session.get(GameOutcome, game_id) is not None:
        return False

    latest_time_update = get_latest_time_update(session, game_id)
    if not latest_time_update or not latest_time_update.ticking_side:
        return False

    game = session.get(Game, game_id)
    timeout_delta_threshold = -60000 if game and game.external_uploader_ref else 0  # 1 minute grace time for external games to account for delays

    now_dt = datetime.now(UTC)
    time_remainders = latest_time_update.get_actual_time_remainders(now_dt)
    timeout_delta_ms = time_remainders[latest_time_update.ticking_side]
    if timeout_delta_ms <= timeout_delta_threshold:
        timeout_dt = now_dt + timedelta(milliseconds=timeout_delta_ms)
        winner = latest_time_update.ticking_side.opposite()
        await end_game(session, state, secret_config, game_id, OutcomeKind.TIMEOUT, winner, timeout_dt)
        return True

    return False


async def cancel_all_active_offers(session: Session, state: MutableState, game_id: int, ply_dt: datetime) -> None:
    for offer_event in get_active_offers(session, game_id):
        cancel_event = GameOfferEvent(
            occurred_at=ply_dt,
            action=OfferAction.CANCEL,
            offer_kind=offer_event.offer_kind,
            offer_author=offer_event.offer_author,
            game_id=game_id
        )
        session.add(cancel_event)

        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.OFFER_ACTION_PERFORMED,
            model_cast(cancel_event, OfferActionBroadcastedData),
            GameEventChannel(game_id=game_id)
        )
    session.commit()
