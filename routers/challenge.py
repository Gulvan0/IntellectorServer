import random
from typing import assert_never
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import and_, col, or_, select, Session, func

from globalstate import GlobalState, UserReference
from models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengePublic, PlayerRestriction
from models.challenge import ChallengeCreateResponse, ChallengeFischerTimeControl, ChallengeFischerTimeControlCreate
from models.channel import GameListEventChannel, IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, StartedPlayerGamesEventChannel
from models.game import Game, GamePublic, GameStartDetailsPublic
from models.other import Id
from models.player import Player
from routers.utils import USER_TOKEN_HEADER_SCHEME, EarlyResponse, get_session, supports_early_responses
from rules import DEFAULT_STARTING_SIP, Position
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, TimeControlKind, UserRestrictionKind
from utils.fastapi_wrappers import WebsocketOutgoingEventRegistry
from utils.query import exists, not_expired

router = APIRouter(prefix="/challenge")


# In some other places...
# TODO: Cancel all challenges when a server is shutting down
# TODO: Broadcast shutdown announcement to everyone


def _is_player_banned_in_ranked(session: Session, caller: UserReference) -> bool:
    return exists(session, select(
        PlayerRestriction
    ).where(
        PlayerRestriction.kind == UserRestrictionKind.RATED_GAMES,
        PlayerRestriction.login == caller.login,
        not_expired(PlayerRestriction.expires)
    ))


def _get_time_control_equality_conditions(challenge_time_control: ChallengeFischerTimeControlCreate | None) -> list[bool]:
    if challenge_time_control is None:
        return [Challenge.fischer_time_control == None]
    return [
        Challenge.fischer_time_control != None,
        Challenge.fischer_time_control.start_seconds == challenge_time_control.start_seconds,  # type: ignore
        Challenge.fischer_time_control.increment_seconds == challenge_time_control.increment_seconds,  # type: ignore
    ]


def _disable_ranked_bracket_if_necessary(challenge: ChallengeCreateOpen | ChallengeCreateDirect, session: Session, caller: UserReference) -> None:
    if challenge.rated and (caller.is_guest() or _is_player_banned_in_ranked(session, caller)):
        challenge.rated = False


def _disable_special_conditions_if_rated(challenge: ChallengeCreateOpen | ChallengeCreateDirect) -> None:
    if challenge.rated:
        challenge.custom_starting_sip = None
        challenge.acceptor_color = ChallengeAcceptorColor.RANDOM


def _validate_starting_position(challenge: ChallengeCreateOpen | ChallengeCreateDirect) -> None:
    if challenge.custom_starting_sip:
        if challenge.custom_starting_sip == DEFAULT_STARTING_SIP:
            challenge.custom_starting_sip = None
        elif not Position.from_sip(challenge.custom_starting_sip).is_valid_starting():
            raise HTTPException(status_code=400, detail="Invalid starting situation")


def _validate_spam_limits(
    challenge: ChallengeCreateDirect | ChallengeCreateOpen,
    caller: UserReference,
    session: Session
):
    total_active_challenges = session.exec(select(
        func.count(col(Challenge.id))
    ).where(
        Challenge.active,
        Challenge.caller_ref == caller.reference
    )).one()
    max_total = GlobalState.main_config.limits.max_total_active_challenges
    if total_active_challenges >= max_total:
        raise HTTPException(status_code=400, detail=f"Too many active challenges (present {total_active_challenges}, max {max_total})")

    if isinstance(challenge, ChallengeCreateDirect):
        same_callee_active_challenges = session.exec(select(
            func.count(col(Challenge.id))
        ).where(
            Challenge.active,
            Challenge.caller_ref == caller.reference,
            Challenge.kind == ChallengeKind.DIRECT,
            Challenge.callee_ref == challenge.callee_ref
        )).one()
        max_same_callee = GlobalState.main_config.limits.max_same_callee_active_challenges
        if total_active_challenges >= max_total:
            raise HTTPException(
                status_code=400,
                detail=f"Too many active direct challenges to {challenge.callee_ref} (present {same_callee_active_challenges}, max {max_same_callee})"
            )


def _perform_common_validations(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: Session
) -> None:
    if GlobalState.shutdown_activated:
        raise HTTPException(status_code=503, detail="Server is preparing to be restarted")
    _validate_spam_limits(challenge, caller, session)
    _disable_ranked_bracket_if_necessary(challenge, session, caller)
    _disable_special_conditions_if_rated(challenge)
    _validate_starting_position(challenge)


def _validate_open_uniqueness(
    challenge: ChallengeCreateOpen,
    caller: UserReference,
    session: Session,
    time_control_equality_conditions: list[bool]
) -> None:
    identical_challenge = session.exec(select(
        Challenge
    ).where(
        Challenge.active,
        Challenge.acceptor_color == challenge.acceptor_color,
        Challenge.caller_ref == caller.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
        *time_control_equality_conditions
    )).first()
    if identical_challenge:
        raise HTTPException(status_code=400, detail=f"Challenge already exists ({identical_challenge.id})")


def _validate_direct_uniqueness(
    challenge: ChallengeCreateDirect,
    caller: UserReference,
    session: Session,
    time_control_equality_conditions: list[bool]
) -> None:
    identical_challenge = session.exec(select(
        Challenge
    ).where(
        Challenge.active,
        Challenge.acceptor_color == challenge.acceptor_color,
        Challenge.caller_ref == caller.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
        Challenge.kind == ChallengeKind.DIRECT,
        Challenge.callee_ref == challenge.callee_ref,
        *time_control_equality_conditions
    )).first()
    if identical_challenge:
        raise HTTPException(status_code=400, detail=f"Challenge already exists ({identical_challenge.id})")


def _validate_direct_callee_returning_online_status(
    challenge: ChallengeCreateDirect,
    caller: UserReference,
    session: Session
) -> bool:
    if challenge.callee_ref == caller.reference:
        raise HTTPException(status_code=400, detail="Callee and caller cannot be the same user")

    callee = UserReference(challenge.callee_ref)
    if callee.is_guest() and callee.guest_id > GlobalState.last_guest_id:
        raise HTTPException(status_code=404, detail=f"Guest not found: {callee.guest_id}")
    else:
        db_callee = session.get(Player, callee.login)
        if not db_callee:
            raise HTTPException(status_code=404, detail=f"Player not found: {callee.login}")

    direct_challenges_observer_channel = IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
    return GlobalState.ws_subscribers.has_user_subscriber(callee, direct_challenges_observer_channel)


def _get_mergeable_challenge(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: Session,
    time_control_equality_conditions: list[bool]
) -> Challenge | None:
    if isinstance(challenge, ChallengeCreateOpen) and challenge.link_only:
        return None

    query = select(
        Challenge
    ).where(
        Challenge.active,
        Challenge.acceptor_color.mergeable_with(challenge.acceptor_color),
        Challenge.caller_ref != caller.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
        or_(
            Challenge.kind == ChallengeKind.PUBLIC,
            and_(
                Challenge.kind == ChallengeKind.DIRECT,
                Challenge.callee_ref == caller.reference
            )
        ),
        *time_control_equality_conditions
    ).order_by(
        col(Challenge.created_at)
    )

    if isinstance(challenge, ChallengeCreateDirect):
        query = query.where(Challenge.caller_ref == challenge.callee_ref)

    return session.exec(query).first()


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
        case _:
            assert_never(acceptor_color)


async def __create_game(challenge: Challenge, acceptor: UserReference, session: Session) -> GamePublic:
    white_player_ref, black_player_ref = _assign_player_colors(challenge.acceptor_color, challenge.caller_ref, acceptor.reference)

    db_game = Game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control_kind=TimeControlKind.of(challenge.fischer_time_control),
        rated=challenge.rated,
        custom_starting_sip=challenge.custom_starting_sip,
        fischer_time_control=challenge.fischer_time_control,
    )
    session.add(db_game)

    challenge.active = False
    challenge.resulting_game = db_game
    session.add(challenge)

    session.commit()

    assert challenge.id
    challenge_id = Id(id=challenge.id)
    public_game = GamePublic.model_construct(**db_game.model_dump())

    if challenge.kind == ChallengeKind.PUBLIC:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.PUBLIC_CHALLENGE_FULFILLED,
            challenge_id,
            PublicChallengeListEventChannel()
        )
    elif challenge.kind == ChallengeKind.DIRECT:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_FULFILLED,
            challenge_id,
            IncomingChallengesEventChannel(user_ref=acceptor.reference)
        )
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_ACCEPTED,
            challenge_id,
            OutgoingChallengesEventChannel(user_ref=challenge.caller_ref)
        )

    for player_ref in [white_player_ref, black_player_ref]:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.GAME_STARTED,
            public_game,
            StartedPlayerGamesEventChannel(watched_ref=player_ref)
        )
    await GlobalState.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_ACTIVE_GAME,
        GameStartDetailsPublic.model_construct(**public_game.model_dump()),
        GameListEventChannel()
    )

    return public_game


async def _attempt_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: Session,
    time_control_equality_conditions: list[bool]
) -> None:
    mergeable_challenge = _get_mergeable_challenge(challenge, caller, session, time_control_equality_conditions)
    if mergeable_challenge:
        db_game = await __create_game(mergeable_challenge, caller, session)
        response = ChallengeCreateResponse(result="merged", game=db_game)
        raise EarlyResponse(status_code=200, body=response)


@supports_early_responses()
@router.post("/create/open", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_open_challenge(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateOpen):
    caller = GlobalState.token_to_user.get(token)
    if not caller:
        raise HTTPException(status_code=401, detail="Invalid token")

    challenge_kind = ChallengeKind.LINK_ONLY if challenge.link_only else ChallengeKind.PUBLIC
    time_control_equality_conditions = _get_time_control_equality_conditions(challenge.fischer_time_control)

    _perform_common_validations(challenge, caller, session)
    _validate_open_uniqueness(challenge, caller, session, time_control_equality_conditions)
    await _attempt_merging(challenge, caller, session, time_control_equality_conditions)

    db_challenge = Challenge(
        acceptor_color=challenge.acceptor_color,
        custom_starting_sip=challenge.custom_starting_sip,
        rated=challenge.rated,
        caller_ref=caller.reference,
        kind=challenge_kind,
        time_control_kind=TimeControlKind.of(challenge.fischer_time_control),
        fischer_time_control=ChallengeFischerTimeControl.from_create_model(challenge.fischer_time_control)
    )
    session.add(db_challenge)
    session.commit()

    public_challenge = ChallengePublic.model_construct(**db_challenge.model_dump())
    if challenge_kind == ChallengeKind.PUBLIC:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.NEW_PUBLIC_CHALLENGE,
            public_challenge,
            PublicChallengeListEventChannel()
        )
    return ChallengeCreateResponse(result="created", challenge=public_challenge)


@supports_early_responses()
@router.post("/create/direct", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_direct_challenge(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateDirect):
    caller = GlobalState.token_to_user.get(token)
    if not caller:
        raise HTTPException(status_code=401, detail="Invalid token")

    time_control_equality_conditions = _get_time_control_equality_conditions(challenge.fischer_time_control)

    _perform_common_validations(challenge, caller, session)
    _validate_direct_uniqueness(challenge, caller, session, time_control_equality_conditions)
    callee_online = _validate_direct_callee_returning_online_status(challenge, caller, session)
    await _attempt_merging(challenge, caller, session, time_control_equality_conditions)

    db_challenge = Challenge(
        acceptor_color=challenge.acceptor_color,
        custom_starting_sip=challenge.custom_starting_sip,
        rated=challenge.rated,
        caller_ref=caller.reference,
        callee_ref=challenge.callee_ref,
        kind=ChallengeKind.DIRECT,
        time_control_kind=TimeControlKind.of(challenge.fischer_time_control),
        fischer_time_control=ChallengeFischerTimeControl.from_create_model(challenge.fischer_time_control)
    )
    session.add(db_challenge)
    session.commit()

    public_challenge = ChallengePublic.model_construct(**db_challenge.model_dump())
    await GlobalState.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_RECEIVED,
        public_challenge,
        IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
    )
    return ChallengeCreateResponse(result="created", challenge=public_challenge, callee_online=callee_online)


@router.get("/{id}", response_model=ChallengePublic)
async def get_challenge(*, session: Session = Depends(get_session), id: int):
    db_challenge = session.get(Challenge, id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return db_challenge


@router.delete("/{id}")
async def cancel_challenge(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), id: int):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")

    db_challenge = session.get(Challenge, id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=400, detail="Challenge is already inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.caller_ref != client.reference:
        raise HTTPException(status_code=403, detail="Only the author of this challenge may cancel it")

    db_challenge.active = False
    session.add(db_challenge)
    session.commit()

    if db_challenge.kind == ChallengeKind.PUBLIC:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.PUBLIC_CHALLENGE_CANCELLED,
            Id(id=id),
            PublicChallengeListEventChannel()
        )
    elif db_challenge.kind == ChallengeKind.DIRECT and db_challenge.callee_ref:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_CANCELLED,
            Id(id=id),
            IncomingChallengesEventChannel(user_ref=db_challenge.callee_ref)
        )

# TODO: Get open challenges with pagination

# TODO: Get direct (both incoming and outgoing) challenges + expose for websocket (channel refresh operation)


@router.post("/{id}/accept", response_model=GamePublic)
async def accept_challenge(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), id: int):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")

    db_challenge = session.get(Challenge, id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=400, detail="Challenge is inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.kind == ChallengeKind.DIRECT:
        if db_challenge.callee_ref != client.reference:
            raise HTTPException(status_code=403, detail="You are not the callee of this challenge")
    else:
        if db_challenge.caller_ref == client.reference:
            raise HTTPException(status_code=400, detail="Cannot accept own challenge")

    db_game = await __create_game(db_challenge, client, session)

    await GlobalState.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_ACCEPTED,
        Id(id=id),
        OutgoingChallengesEventChannel(user_ref=db_challenge.caller_ref)
    )

    if db_challenge.kind == ChallengeKind.DIRECT:
        await GlobalState.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_FULFILLED,
            Id(id=id),
            IncomingChallengesEventChannel(user_ref=client.reference)
        )

    return db_game

# TODO: Decline challenge - notification is sent
