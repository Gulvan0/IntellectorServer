from datetime import UTC, datetime

from challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from challenge.models import Challenge
from common.models import Id
from common.user_ref import UserReference
from config.models import SecretConfig
from game.methods.cast import to_public_game
from game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from notification.methods import delete_new_public_challenge_notifications, send_game_started_notifications
from pubsub.models.channel import GameListEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, StartedPlayerGamesEventChannel
from game.models.main import Game, GamePublic, GameStartedBroadcastedData
from game.models.time_control import GameFischerTimeControl
from net.core import MutableState
from common.time_control import FischerTimeControlEntity, TimeControlKind
from pubsub.outgoing_event.update import GameStarted, NewActiveGame, OutgoingChallengeAccepted, PublicChallengeFulfilled
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
    deactivated_challenge: Challenge | None = None
) -> GamePublic:
    started_at = datetime.now(UTC)

    db_game = Game(
        started_at=started_at,
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control_kind=TimeControlKind.of(time_control),
        rated=rated,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=external_uploader_ref,
        fischer_time_control=GameFischerTimeControl(
            start_seconds=time_control.start_seconds,
            increment_seconds=time_control.increment_seconds
        ) if time_control else None
    )
    session.add(db_game)

    if time_control:
        session.add(GameTimeUpdate(
            updated_at=started_at,
            white_ms=time_control.start_seconds * 1000,
            black_ms=time_control.start_seconds * 1000,
            ticking_side=None,
            reason=GameTimeUpdateReason.INIT,
            game=db_game
        ))

    if deactivated_challenge:
        deactivated_challenge.active = False
        deactivated_challenge.resulting_game = db_game
        session.add(deactivated_challenge)

    await session.commit()

    public_game = await to_public_game(session, db_game)

    for player_ref in [white_player_ref, black_player_ref]:
        game_started_event = GameStarted(public_game, StartedPlayerGamesEventChannel(watched_ref=player_ref))
        await state.ws_subscribers.broadcast(game_started_event)

    new_game_event = NewActiveGame(GameStartedBroadcastedData.cast(public_game), GameListEventChannel())
    await state.ws_subscribers.broadcast(new_game_event)

    return public_game


async def create_internal_game(
    challenge: Challenge,
    acceptor: UserReference,
    session: AsyncSession,
    state: MutableState,
    secret_config: SecretConfig
) -> GamePublic:
    white_player_ref, black_player_ref = assign_player_colors(challenge.acceptor_color, challenge.caller_ref, acceptor.reference)

    public_game = await create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=challenge.fischer_time_control,
        rated=challenge.rated,
        custom_starting_sip=challenge.custom_starting_sip,
        external_uploader_ref=None,
        session=session,
        state=state,
        deactivated_challenge=challenge
    )

    assert challenge.id

    await delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    event_payload = Id(id=challenge.id)

    if challenge.kind == ChallengeKind.PUBLIC:
        fulfill_event = PublicChallengeFulfilled(event_payload, PublicChallengeListEventChannel())
        await state.ws_subscribers.broadcast(fulfill_event)

    accept_event = OutgoingChallengeAccepted(event_payload, OutgoingChallengesEventChannel(user_ref=challenge.caller_ref))
    await state.ws_subscribers.broadcast(accept_event)

    await send_game_started_notifications(
        white_player_ref,
        black_player_ref,
        public_game,
        secret_config.integrations,
        session
    )

    return public_game


async def create_external_game(
    uploader: UserReference,
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    custom_starting_sip: str | None,
    session: AsyncSession,
    state: MutableState
) -> GamePublic:
    return await create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=time_control,
        rated=False,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=uploader.reference,
        session=session,
        state=state
    )
