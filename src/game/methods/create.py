from datetime import UTC, datetime

from board.constants.sip import DEFAULT_STARTING_SIP
from challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from challenge.models import Challenge
from common.models import Id
from common.user_ref import UserReference
from config.models import MainConfig, SecretConfig
from game.methods.timeout import plan_timeout_check
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from notification.methods import delete_new_public_challenge_notifications, send_game_started_notifications
from player.methods import get_ranked_game_stats_for_time_control, resolve_player_refs
from pubsub.models.channel import CurrentGameListEventChannel, IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, PlayerOngoingGamesEventChannel
from game.models.main import Game, GameSummaryPublic
from game.models.time_control import GameFischerTimeControl
from net.state import MutableState
from common.time_control import FischerTimeControlEntity, TimeControlKind
from pubsub.outgoing_event.update import IncomingChallengeAccepted, NewActiveGame, OngoingGameStarted, OutgoingChallengeAccepted, PublicChallengeFulfilled
from utils.async_orm_session import AsyncSession

import random


def assign_player_colors(
    acceptor_color: ChallengeAcceptorColor,
    caller_ref: str,
    acceptor_ref: str
) -> tuple[str, str]:
    match acceptor_color:
        case ChallengeAcceptorColor.RANDOM:
            return random.choice([
                (caller_ref, acceptor_ref),
                (acceptor_ref, caller_ref)
            ])
        case ChallengeAcceptorColor.WHITE:
            return acceptor_ref, caller_ref
        case ChallengeAcceptorColor.BLACK:
            return caller_ref, acceptor_ref


async def create_game(
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    rated: bool,
    custom_starting_sip: str | None,
    external_uploader_ref: str | None,
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig,
    deactivated_challenge: Challenge | None = None
) -> GameSummaryPublic:
    if deactivated_challenge:
        caller = UserReference(deactivated_challenge.caller_ref)
        cancel_timer = state.user_challenge_cancelling_timers.get(UserReference.guest(caller.guest_id) if caller.is_guest() else UserReference.logged(caller.login))
        if cancel_timer:
            cancel_timer.cancel()

    started_at = datetime.now(UTC)
    starting_sip = custom_starting_sip or DEFAULT_STARTING_SIP
    time_control_kind = TimeControlKind.of(time_control)

    # the ratings the game is played at; guests have none
    elo_snapshots: dict[str, tuple[int, bool] | None] = {}
    for player_ref in (white_player_ref, black_player_ref):
        reference = UserReference(player_ref)
        if reference.is_player():
            stats = await get_ranked_game_stats_for_time_control(session, main_config, reference.login, time_control_kind)
            elo_snapshots[player_ref] = (stats.elo or main_config.elo.default, stats.is_elo_provisional)
        else:
            elo_snapshots[player_ref] = None
    white_elo = elo_snapshots[white_player_ref]
    black_elo = elo_snapshots[black_player_ref]

    db_time_control = GameFischerTimeControl(
        start_seconds=time_control.start_seconds,
        increment_seconds=time_control.increment_seconds
    ) if time_control else None

    db_game = Game(
        started_at=started_at,
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control_kind=time_control_kind,
        rated=rated,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=external_uploader_ref,
        latest_sip=starting_sip,
        opening_sip=starting_sip,
        white_elo=white_elo[0] if white_elo else None,
        white_elo_provisional=white_elo[1] if white_elo else None,
        black_elo=black_elo[0] if black_elo else None,
        black_elo_provisional=black_elo[1] if black_elo else None,
        fischer_time_control=db_time_control
    )
    session.add(db_game)

    initial_time_update = GameTimeUpdate(
        updated_at=started_at,
        white_ms=time_control.start_seconds * 1000,
        black_ms=time_control.start_seconds * 1000,
        ticking_side=None,
        reason=GameTimeUpdateReason.INIT,
        game=db_game
    ) if time_control else None
    if initial_time_update:
        session.add(initial_time_update)

    if deactivated_challenge:
        deactivated_challenge.active = False
        deactivated_challenge.resulting_game = db_game
        session.add(deactivated_challenge)

    await session.commit()

    await session.refresh(db_game)
    if db_time_control:
        await session.refresh(db_time_control)

    if initial_time_update:
        assert db_game.id
        await session.refresh(initial_time_update)  # the commit expired it, and an async session can't reload it lazily
        await plan_timeout_check(
            state,
            main_config,
            secret_config,
            triggering_time_update=initial_time_update,
            game_id=db_game.id,
            is_external=external_uploader_ref is not None
        )

    collected_refs = db_game.collect_refs(include_nested=False)
    resolved_refs = await resolve_player_refs(collected_refs, session)
    summary = db_game.to_summary_as_new(resolved_refs, db_time_control)

    for player_ref in [white_player_ref, black_player_ref]:
        game_started_event = OngoingGameStarted(summary, PlayerOngoingGamesEventChannel(watched_ref=player_ref))
        state.concurrent_tasks.plan(state.ws_subscribers.broadcast(game_started_event))

    new_game_event = NewActiveGame(summary, CurrentGameListEventChannel())
    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(new_game_event))

    return summary


async def create_internal_game(
    challenge: Challenge,
    acceptor: UserReference,
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig
) -> GameSummaryPublic:
    white_player_ref, black_player_ref = assign_player_colors(challenge.acceptor_color, challenge.caller_ref, acceptor.reference)

    # read before create_game commits: committing expires the challenge, and it can't be lazily reloaded here
    assert challenge.id
    challenge_id = challenge.id
    challenge_kind = challenge.kind
    caller_ref = challenge.caller_ref

    public_game = await create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=challenge.fischer_time_control,
        rated=challenge.rated,
        custom_starting_sip=challenge.custom_starting_sip,
        external_uploader_ref=None,
        session=session,
        state=state,
        main_config=main_config,
        secret_config=secret_config,
        deactivated_challenge=challenge
    )

    state.concurrent_tasks.plan_with_own_session(lambda task_session: delete_new_public_challenge_notifications(
        challenge_id=challenge_id,
        session=task_session,
        vk_token=secret_config.integrations.vk.token
    ))

    event_payload = Id(id=challenge_id)

    if challenge_kind == ChallengeKind.PUBLIC:
        fulfill_event = PublicChallengeFulfilled(event_payload, PublicChallengeListEventChannel())
        state.concurrent_tasks.plan(state.ws_subscribers.broadcast(fulfill_event))

    accept_event = OutgoingChallengeAccepted(event_payload, OutgoingChallengesEventChannel(user_ref=caller_ref))
    state.concurrent_tasks.plan(state.ws_subscribers.broadcast(accept_event))

    if challenge_kind == ChallengeKind.DIRECT:
        incoming_accept_event = IncomingChallengeAccepted(event_payload, IncomingChallengesEventChannel(user_ref=acceptor.reference))
        state.concurrent_tasks.plan(state.ws_subscribers.broadcast(incoming_accept_event))

    state.concurrent_tasks.plan_with_own_session(lambda task_session: send_game_started_notifications(
        white_player_ref,
        black_player_ref,
        public_game,
        secret_config.integrations,
        task_session
    ))

    return public_game


async def create_external_game(
    uploader: UserReference,
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    custom_starting_sip: str | None,
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig
) -> GameSummaryPublic:
    return await create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=time_control,
        rated=False,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=uploader.reference,
        session=session,
        state=state,
        main_config=main_config,
        secret_config=secret_config
    )
