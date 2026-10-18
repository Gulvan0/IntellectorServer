import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import col, desc, select

from config.models import MainConfig, SecretConfig
from game.methods.end import end_game
from game.models.main import Game
from game.methods.get import get_latest_time_update
from game.datatypes import OutcomeKind
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from log.models import TimeoutCheckExecutedLog, TimeoutCheckPlannedLog
from net.state import MutableState
from board.piece import PieceColor
from utils.async_orm_session import AsyncSession

import time


# Time updates after which the side to move has a first-move deadline instead of a ticking clock
FIRST_MOVE_DEADLINE_REASONS = (GameTimeUpdateReason.INIT, GameTimeUpdateReason.PLY, GameTimeUpdateReason.ROLLBACK)


@dataclass
class TimeoutCheckResult:
    occurred_at: datetime
    remaining_ms: int
    is_external: bool
    game_aborted: bool


def first_move_deadline_secs(main_config: MainConfig, is_external: bool) -> int:
    return main_config.rules.external_first_move_deadline_secs if is_external else main_config.rules.first_move_deadline_secs


async def __delay_timeout_check(
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    delay_secs: float,
    game_id: int
) -> None:
    existing_timer_handle = state.game_timeout_check_timers.get(game_id)
    if existing_timer_handle:
        existing_timer_handle.cancel()

    loop = asyncio.get_running_loop()

    async def task(session: AsyncSession) -> None:
        state.game_timeout_check_timers.pop(game_id, None)

        check_output = await check_timeout(
            session=session,
            state=state,
            main_config=main_config,
            secret_config=secret_config,
            game_id=game_id,
        )

        if check_output:
            log_entry = TimeoutCheckExecutedLog(
                event_time=check_output.occurred_at,
                aborted=check_output.game_aborted,
                game_id=game_id,
                remaining_ms=check_output.remaining_ms,
                is_external=check_output.is_external
            )
            session.add(log_entry)
            await session.commit()

    state.game_timeout_check_timers[game_id] = loop.call_later(delay_secs, lambda: state.concurrent_tasks.plan_with_own_session(task))

    async def log_planned(session: AsyncSession) -> None:
        session.add(TimeoutCheckPlannedLog(
            game_id=game_id,
            delay_ms=delay_secs
        ))
        await session.commit()

    state.concurrent_tasks.plan_with_own_session(log_planned)


async def _get_first_move_deadline_start(session: AsyncSession, game_id: int) -> GameTimeUpdate | None:
    """The time update the current first-move deadline is counted from: added time doesn't restart it"""
    result = await session.exec(
        select(GameTimeUpdate)
        .where(
            GameTimeUpdate.game_id == game_id,
            GameTimeUpdate.reason != GameTimeUpdateReason.TIME_ADDED
        )
        .order_by(
            desc(col(GameTimeUpdate.id))
        )
    )
    return result.first()


async def check_timeout(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int,
) -> TimeoutCheckResult | None:
    """Ends the game if its ticking side ran out of time, or aborts it if the side to move missed its first-move deadline;
    otherwise plans the next check"""
    latest_time_update = await get_latest_time_update(session, game_id)
    if not latest_time_update:
        return None

    now_dt = datetime.now(UTC)
    game = await session.get(Game, game_id)
    is_external = bool(game and game.external_uploader_ref)

    if not latest_time_update.ticking_side:
        deadline_start = await _get_first_move_deadline_start(session, game_id)
        if not deadline_start or deadline_start.reason not in FIRST_MOVE_DEADLINE_REASONS or not deadline_start.updated_at:
            return None

        deadline_dt = deadline_start.updated_at.replace(tzinfo=UTC) + timedelta(seconds=first_move_deadline_secs(main_config, is_external))
        remaining_ms = int((deadline_dt - now_dt).total_seconds() * 1000)
        if remaining_ms <= 0:
            await end_game(
                session,
                state,
                main_config,
                secret_config,
                game_id,
                OutcomeKind.ABORT,
                None,
                deadline_dt,
                pre_retrieved_db_game=game,
                pre_retrieved_latest_time_update=latest_time_update
            )
            return TimeoutCheckResult(now_dt, remaining_ms, is_external, True)

        await __delay_timeout_check(state, main_config, secret_config, remaining_ms / 1000 + 0.01, game_id)
        return TimeoutCheckResult(now_dt, remaining_ms, is_external, False)

    timeout_delta_threshold = -60000 if is_external else 0  # 1 minute grace time for external games to account for delays

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
        return TimeoutCheckResult(now_dt, timeout_delta_ms, is_external, True)
    else:
        await __delay_timeout_check(state, main_config, secret_config, (timeout_delta_ms - timeout_delta_threshold) / 1000 + 0.01, game_id)

    return TimeoutCheckResult(now_dt, timeout_delta_ms, is_external, False)


async def plan_timeout_check(
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    *,
    triggering_time_update: GameTimeUpdate,
    game_id: int,
    is_external: bool,
) -> None:
    """Plans the check of the time update's ticking side running out of time or, while no clock ticks yet,
    of the side to move missing its first-move deadline"""
    if not triggering_time_update.updated_at:
        return
    passed_secs = time.time() - triggering_time_update.updated_at.replace(tzinfo=UTC).timestamp()

    if not triggering_time_update.ticking_side:
        if triggering_time_update.reason not in FIRST_MOVE_DEADLINE_REASONS:
            return
        delay_secs = first_move_deadline_secs(main_config, is_external) - passed_secs + 0.01
    else:
        remainder_ms = triggering_time_update.white_ms if triggering_time_update.ticking_side == PieceColor.WHITE else triggering_time_update.black_ms
        grace_period_secs = 60 if is_external else 0
        delay_secs = remainder_ms / 1000 - passed_secs + grace_period_secs + 0.01

    await __delay_timeout_check(state, main_config, secret_config, delay_secs, game_id)


async def replan_all_timeout_checks(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig
) -> None:
    """Restores the in-memory timers of all ongoing timed games after a launch, ending the overdue ones"""
    result = await session.exec(
        select(Game.id)
        .where(
            Game.outcome == None,  # noqa
            Game.fischer_time_control != None  # noqa
        )
    )
    for game_id in list(result.all()):
        if game_id is not None:
            await check_timeout(session, state, main_config, secret_config, game_id)
