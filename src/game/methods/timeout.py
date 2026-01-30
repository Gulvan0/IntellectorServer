import asyncio
from datetime import UTC, datetime, timedelta

from config.models import MainConfig, SecretConfig
from game.methods.update import end_game
from game.models.main import Game
from game.models.outcome import GameOutcome
from game.methods.get import get_latest_time_update
from game.datatypes import OutcomeKind
from game.models.time_update import GameTimeUpdate
from net.core import MutableState
from board.piece import PieceColor
from utils.async_orm_session import AsyncSession

import time


async def __delay_timeout_check(
    delay_secs: float,
    game_id: int,
    outcome_abscence_checked: bool = False
) -> None:
    from main import app

    existing_timer_handle = app.mutable_state.game_timeout_check_timers.get(game_id)
    if existing_timer_handle:
        existing_timer_handle.cancel()

    loop = asyncio.get_running_loop()

    async def task():
        app.mutable_state.game_timeout_check_timers.pop(game_id, None)

        async with app.get_db_session() as session:
            return await check_timeout(
                session=session,
                state=app.mutable_state,
                main_config=app.main_config,
                secret_config=app.secret_config,
                game_id=game_id,
                outcome_abscence_checked=outcome_abscence_checked,
            )

    app.mutable_state.game_timeout_check_timers[game_id] = loop.call_later(delay_secs, lambda: asyncio.create_task(task()))


async def check_timeout(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int,
    outcome_abscence_checked: bool = False,
) -> bool:
    if not outcome_abscence_checked:
        existing_outcome = await session.get(GameOutcome, game_id)
        if existing_outcome is not None:
            return False

    latest_time_update = await get_latest_time_update(session, game_id)
    if not latest_time_update or not latest_time_update.ticking_side:
        return False

    game = await session.get(Game, game_id)
    timeout_delta_threshold = -60000 if game and game.external_uploader_ref else 0  # 1 minute grace time for external games to account for delays

    now_dt = datetime.now(UTC)
    time_remainders = latest_time_update.get_actual_time_remainders(now_dt)
    timeout_delta_ms = time_remainders[latest_time_update.ticking_side]
    if timeout_delta_ms <= timeout_delta_threshold:
        timeout_dt = now_dt + timedelta(milliseconds=timeout_delta_ms)
        winner = latest_time_update.ticking_side.opposite()
        await end_game(
            session,
            state,
            main_config,
            secret_config,
            game_id,
            OutcomeKind.TIMEOUT,
            winner,
            timeout_dt,
            pre_retrieved_db_game=game,
            pre_retrieved_latest_time_update=latest_time_update
        )
        return True
    else:
        await __delay_timeout_check((timeout_delta_ms - timeout_delta_threshold) / 1000 + 0.01, game_id)

    return False


async def plan_timeout_check(
    *,
    triggering_time_update: GameTimeUpdate,
    game_id: int,
    is_external: bool,
    outcome_abscence_checked: bool = False,
) -> None:
    if not triggering_time_update.ticking_side:
        return

    remainder_ms = triggering_time_update.white_ms if triggering_time_update.ticking_side == PieceColor.WHITE else triggering_time_update.black_ms
    passed_secs = time.time() - triggering_time_update.updated_at.timestamp()
    grace_period_secs = 60 if is_external else 0
    delay_secs = remainder_ms / 1000 - passed_secs + grace_period_secs + 0.01

    await __delay_timeout_check(delay_secs, game_id, outcome_abscence_checked)
