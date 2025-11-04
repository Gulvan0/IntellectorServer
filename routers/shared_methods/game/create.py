from datetime import UTC, datetime
import random
from sqlmodel import Session
from models.challenge import Challenge
from models.channel import GameListEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, StartedPlayerGamesEventChannel
from models.config import SecretConfig
from models.game import (
    Game,
    GameFischerTimeControl,
    GamePublic,
    GameStartedBroadcastedData,
)
from models.game.time_update import GameTimeUpdate, GameTimeUpdateReason
from models.other import Id
from net.fastapi_wrapper import MutableState
from net.outgoing import WebsocketOutgoingEventRegistry
from routers.shared_methods.game.cast import compose_public_game
from routers.shared_methods.notification import delete_new_public_challenge_notifications, send_game_started_notifications
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, FischerTimeControlEntity, TimeControlKind, UserReference
from utils.query import model_cast


def _assign_player_colors(acceptor_color: ChallengeAcceptorColor, caller_ref: str, acceptor_ref: str) -> tuple[str, str]:
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


async def _create_game(
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    rated: bool,
    custom_starting_sip: str | None,
    external_uploader_ref: str | None,
    session: Session,
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

    session.commit()

    public_game = compose_public_game(session, db_game)

    for player_ref in [white_player_ref, black_player_ref]:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.GAME_STARTED,
            public_game,
            StartedPlayerGamesEventChannel(watched_ref=player_ref)
        )
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_ACTIVE_GAME,
        model_cast(public_game, GameStartedBroadcastedData),
        GameListEventChannel()
    )

    return public_game


async def create_internal_game(challenge: Challenge, acceptor: UserReference, session: Session, state: MutableState, secret_config: SecretConfig) -> GamePublic:
    white_player_ref, black_player_ref = _assign_player_colors(challenge.acceptor_color, challenge.caller_ref, acceptor.reference)

    public_game = await _create_game(
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

    delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    challenge_id = Id(id=challenge.id)

    if challenge.kind == ChallengeKind.PUBLIC:
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

    send_game_started_notifications(white_player_ref, black_player_ref, public_game, secret_config.integrations, session)

    return public_game


async def create_external_game(
    uploader: UserReference,
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    custom_starting_sip: str | None,
    session: Session,
    state: MutableState
) -> GamePublic:
    return await _create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=time_control,
        rated=False,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=uploader.reference,
        session=session,
        state=state
    )
