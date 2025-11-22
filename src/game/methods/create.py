from datetime import UTC, datetime

from src.common.models import Id
from src.common.user_ref import UserReference
from src.config.models import SecretConfig
from src.game.methods.cast import to_public_game
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdateReason
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.pubsub.models import GameListEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, StartedPlayerGamesEventChannel
from src.game.models.main import Game, GamePublic, GameStartedBroadcastedData
from src.game.models.time_control import GameFischerTimeControl, GameFischerTimeControlPublic
from src.net.core import MutableState
from src.common.time_control import FischerTimeControlEntity, TimeControlKind
from src.utils.async_orm_session import AsyncSession
from src.utils.cast import model_cast_optional

import random
import src.challenge.datatypes as challenge_datatypes
import src.challenge.models as challenge_models
import src.notification.methods as notification_methods


def assign_player_colors(
    acceptor_color: challenge_datatypes.ChallengeAcceptorColor,
    caller_ref: str,
    acceptor_ref: str
) -> tuple[str, str]:
    match acceptor_color:
        case challenge_datatypes.ChallengeAcceptorColor.RANDOM:
            return random.choice([
                (caller_ref, acceptor_ref),
                (acceptor_ref, caller_ref)
            ])
        case challenge_datatypes.ChallengeAcceptorColor.WHITE:
            return acceptor_ref, caller_ref
        case challenge_datatypes.ChallengeAcceptorColor.BLACK:
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
    deactivated_challenge: challenge_models.Challenge | None = None
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
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.GAME_STARTED,
            public_game,
            StartedPlayerGamesEventChannel(watched_ref=player_ref)
        )
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_ACTIVE_GAME,
        GameStartedBroadcastedData(
            started_at=public_game.started_at,
            white_player_ref=public_game.white_player_ref,
            black_player_ref=public_game.black_player_ref,
            time_control_kind=public_game.time_control_kind,
            rated=public_game.rated,
            custom_starting_sip=public_game.custom_starting_sip,
            external_uploader_ref=public_game.external_uploader_ref,
            id=public_game.id,
            fischer_time_control=model_cast_optional(public_game.fischer_time_control, GameFischerTimeControlPublic)
        ),
        GameListEventChannel()
    )

    return public_game


async def create_internal_game(
    challenge: challenge_models.Challenge,
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

    await notification_methods.delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    challenge_id = Id(id=challenge.id)

    if challenge.kind == challenge_datatypes.ChallengeKind.PUBLIC:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.PUBLIC_CHALLENGE_FULFILLED,
            challenge_id,
            PublicChallengeListEventChannel()
        )

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_ACCEPTED,
        challenge_id,
        OutgoingChallengesEventChannel(user_ref=challenge.caller_ref)
    )

    await notification_methods.send_game_started_notifications(
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
