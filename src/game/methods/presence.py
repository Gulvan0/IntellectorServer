import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from board.deserializers.sip import color_to_move_from_sip
from board.piece import PieceColor
from common.time_control import TimeControlKind
from config.models import MainConfig, SecretConfig
from game.datatypes import OutcomeKind
from game.methods.end import end_game
from game.methods.event import get_next_event_index
from game.methods.get import get_latest_time_update
from game.methods.ongoing import broadcast_ongoing_game_update
from game.models.main import Game
from game.models.outcome import GameOutcome
from game.models.presence import GameSuspensionBroadcastedData, GameUploaderPresence
from game.models.suspension import GameSuspensionEvent
from game.models.time_control import GameFischerTimeControl
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic, GameTimeUpdateReason
from net.state import MutableState
from pubsub.models.channel import GameEventChannel
from pubsub.outgoing_event.update import GameSuspensionChanged
from utils.async_orm_session import AsyncSession


# An external game is played by its uploader against a bot. When the uploader goes silent while the bot is to move,
# nothing can make the bot move: the game gets suspended (the bot's clock freezes) and, if the uploader doesn't return
# in time, is abandoned by the human. While the human is to move, their clock runs and flags as usual


@dataclass
class GameFacts:
    """What the presence logic needs of an external game, read before any commit expires the loaded game"""
    game_id: int
    bot_color: PieceColor
    time_control_kind: TimeControlKind
    latest_sip: str


async def load_game_facts(session: AsyncSession, game_id: int) -> GameFacts | None:
    """None for a missing game or an internal one"""
    db_game = await session.get(Game, game_id, populate_existing=True)
    if not db_game or not db_game.external_uploader_ref:
        return None
    return GameFacts(game_id, get_bot_color(db_game), db_game.time_control_kind, db_game.latest_sip)


def get_bot_color(db_game: Game) -> PieceColor:
    return PieceColor.BLACK if db_game.external_uploader_ref == db_game.white_player_ref else PieceColor.WHITE


def is_uploader_alive(presence: GameUploaderPresence | None, main_config: MainConfig, now: datetime) -> bool:
    if presence is None or presence.suspended_at is not None:
        return False
    return (now - presence.last_seen_at).total_seconds() < main_config.rules.heartbeat_stale_secs


async def get_suspension_ttl_secs(session: AsyncSession, main_config: MainConfig, facts: GameFacts) -> int:
    if facts.time_control_kind == TimeControlKind.CORRESPONDENCE:
        return main_config.rules.correspondence_suspension_ttl_secs
    time_control = await session.get(GameFischerTimeControl, facts.game_id)
    assert time_control
    return max(time_control.increment_seconds, time_control.start_seconds // 4, main_config.rules.min_suspension_ttl_secs)


async def _change_suspension(
    session: AsyncSession,
    state: MutableState,
    game_id: int,
    presence: GameUploaderPresence,
    suspended: bool,
    time_update: GameTimeUpdate | None,
    now: datetime
) -> None:
    event_index = await get_next_event_index(session, game_id)
    presence.suspended_at = now if suspended else None
    session.add(presence)
    session.add(GameSuspensionEvent(
        occurred_at=now,
        event_index=event_index,
        suspended=suspended,
        game_id=game_id,
        time_update=time_update
    ))
    await session.commit()
    await session.refresh(presence)
    if time_update:
        await session.refresh(time_update)

    data = GameSuspensionBroadcastedData(
        event_index=event_index,
        suspended=suspended,
        last_seen_at=presence.last_seen_at,
        time_update=GameTimeUpdatePublic.cast(time_update)
    )
    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(GameSuspensionChanged(data, GameEventChannel(game_id=game_id))))
    await broadcast_ongoing_game_update(session, state, game_id)


async def _resume(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    facts: GameFacts,
    presence: GameUploaderPresence,
    now: datetime
) -> None:
    from game.methods.timeout import plan_timeout_check  # timeout checks consult the presence in their turn

    game_id = facts.game_id
    bot_color = facts.bot_color
    frozen = await get_latest_time_update(session, game_id)

    time_update = None
    if frozen and frozen.reason == GameTimeUpdateReason.SUSPENDED:
        time_update = GameTimeUpdate(
            updated_at=now,
            white_ms=frozen.white_ms,
            black_ms=frozen.black_ms,
            ticking_side=bot_color,
            reason=GameTimeUpdateReason.RESUMED,
            game_id=game_id
        )

    await _change_suspension(session, state, game_id, presence, False, time_update, now)
    if time_update:
        await plan_timeout_check(
            state,
            main_config,
            secret_config,
            triggering_time_update=time_update,
            game_id=game_id,
            is_external=True
        )


async def touch_uploader(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int
) -> None:
    """Records that the uploader of an external game is alive, resuming the game if it was suspended"""
    facts = await load_game_facts(session, game_id)
    if not facts:
        return

    now = datetime.now(UTC)
    presence = await session.get(GameUploaderPresence, game_id, populate_existing=True)
    was_suspended = bool(presence and presence.suspended_at)
    if presence:
        presence.last_seen_at = now
    else:
        presence = GameUploaderPresence(game_id=game_id, last_seen_at=now)
    session.add(presence)
    await session.commit()
    await session.refresh(presence)

    if was_suspended:
        await _resume(session, state, main_config, secret_config, facts, presence, now)

    await plan_presence_check(state, main_config, secret_config, game_id, presence, await get_suspension_ttl_secs(session, main_config, facts))


async def plan_presence_check(
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int,
    presence: GameUploaderPresence,
    suspension_ttl_secs: int
) -> None:
    """Plans the moment the uploader becomes considered gone, or, once the game is suspended, the moment it gets abandoned"""
    if presence.suspended_at:
        wait_secs = suspension_ttl_secs
    else:
        wait_secs = main_config.rules.heartbeat_stale_secs
    deadline = presence.last_seen_at + timedelta(seconds=wait_secs)
    delay_secs = max((deadline - datetime.now(UTC)).total_seconds(), 0) + 0.01

    existing_timer_handle = state.game_presence_check_timers.get(game_id)
    if existing_timer_handle:
        existing_timer_handle.cancel()

    async def task(session: AsyncSession) -> None:
        state.game_presence_check_timers.pop(game_id, None)
        await check_presence(session, state, main_config, secret_config, game_id)

    loop = asyncio.get_running_loop()
    state.game_presence_check_timers[game_id] = loop.call_later(delay_secs, lambda: state.concurrent_tasks.plan_with_own_session(task))


async def check_presence(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int
) -> None:
    """Suspends the game if its uploader went silent while the bot is to move, abandons it if the uploader doesn't return in time"""
    async with state.game_action(game_id):
        await _check_presence(session, state, main_config, secret_config, game_id)


async def _check_presence(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    game_id: int
) -> None:
    facts = await load_game_facts(session, game_id)
    if not facts:
        return
    existing_outcome = await session.get(GameOutcome, game_id)
    if existing_outcome:
        return

    now = datetime.now(UTC)
    presence = await session.get(GameUploaderPresence, game_id, populate_existing=True)
    if not presence:
        presence = GameUploaderPresence(game_id=game_id, last_seen_at=now)
        session.add(presence)
        await session.commit()
        await session.refresh(presence)

    ttl_secs = await get_suspension_ttl_secs(session, main_config, facts)
    bot_color = facts.bot_color
    last_seen_at = presence.last_seen_at
    silence_secs = (now - last_seen_at).total_seconds()

    if presence.suspended_at:
        if silence_secs >= ttl_secs:
            await end_game(session, state, main_config, secret_config, game_id, OutcomeKind.ABANDON, bot_color, now)
        else:
            await plan_presence_check(state, main_config, secret_config, game_id, presence, ttl_secs)
        return

    if silence_secs < main_config.rules.heartbeat_stale_secs:
        await plan_presence_check(state, main_config, secret_config, game_id, presence, ttl_secs)
        return

    if color_to_move_from_sip(facts.latest_sip) != bot_color:
        return  # the human's turn: their own clock decides; the uploader's next call plans the check again

    time_update = None
    latest = await get_latest_time_update(session, game_id)
    if latest and latest.ticking_side == bot_color:
        frozen_at = max(last_seen_at, latest.updated_at) if latest.updated_at else last_seen_at
        remainders = latest.get_actual_time_remainders(frozen_at)
        time_update = GameTimeUpdate(
            updated_at=now,
            white_ms=max(0, remainders[PieceColor.WHITE]),
            black_ms=max(0, remainders[PieceColor.BLACK]),
            ticking_side=None,
            reason=GameTimeUpdateReason.SUSPENDED,
            game_id=game_id
        )

    await _change_suspension(session, state, game_id, presence, True, time_update, now)
    await plan_presence_check(state, main_config, secret_config, game_id, presence, ttl_secs)


async def replan_all_presence_checks(
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig
) -> None:
    """Restores the in-memory timers after a launch. The downtime doesn't count against the uploaders: their games count as seen now"""
    result = await session.exec(
        select(Game.id)
        .outerjoin(GameOutcome)
        .where(
            GameOutcome.game_id == None,  # noqa
            Game.external_uploader_ref != None  # noqa
        )
    )
    for game_id in list(result.all()):
        if game_id is None:
            continue
        facts = await load_game_facts(session, game_id)
        if not facts:
            continue
        presence = await session.get(GameUploaderPresence, game_id, populate_existing=True)
        if presence is None:
            presence = GameUploaderPresence(game_id=game_id, last_seen_at=datetime.now(UTC))
        else:
            presence.last_seen_at = datetime.now(UTC)
        session.add(presence)
        await session.commit()
        await session.refresh(presence)
        await plan_presence_check(state, main_config, secret_config, game_id, presence, await get_suspension_ttl_secs(session, main_config, facts))
