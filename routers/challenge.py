from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import and_, col, or_, select, Session, func

from globalstate import GlobalState, UserReference
from models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengePublic, PlayerRestriction
from models.challenge import ChallengeCreateResponse, ChallengeFischerTimeControl, ChallengeFischerTimeControlCreate
from models.player import Player
from routers.utils import EarlyResponse, get_session, OPTIONAL_USER_TOKEN_HEADER_SCHEME, supports_early_responses
from rules import DEFAULT_STARTING_SIP, Position
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, TimeControlKind, UserRestrictionKind
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

    # TODO: check player online and incorporate this info into the response
    return False


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


def _attempt_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: Session,
    time_control_equality_conditions: list[bool]
) -> None:
    mergeable_challenge = _get_mergeable_challenge(challenge, caller, session, time_control_equality_conditions)
    if mergeable_challenge:
        ...  # TODO: Cancel all outgoing challenges, create, add, commit db_game
        response = ChallengeCreateResponse(result="merged", game=None)  # replace None with db_game
        raise EarlyResponse(status_code=200, body=response)


@supports_early_responses()
@router.post("/create/open", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_open_challenge(*, session: Session = Depends(get_session), token: str = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateOpen):
    caller = GlobalState.token_to_user.get(token)
    if not caller:
        raise HTTPException(status_code=401, detail="Invalid token")

    challenge_kind = ChallengeKind.LINK_ONLY if challenge.link_only else ChallengeKind.PUBLIC
    time_control_equality_conditions = _get_time_control_equality_conditions(challenge.fischer_time_control)

    _perform_common_validations(challenge, caller, session)
    _validate_open_uniqueness(challenge, caller, session, time_control_equality_conditions)
    _attempt_merging(challenge, caller, session, time_control_equality_conditions)

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
    return ChallengeCreateResponse(result="created", challenge=ChallengePublic.model_validate(db_challenge))


@supports_early_responses()
@router.post("/create/direct", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_direct_challenge(*, session: Session = Depends(get_session), token: str = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME), challenge: ChallengeCreateDirect):
    caller = GlobalState.token_to_user.get(token)
    if not caller:
        raise HTTPException(status_code=401, detail="Invalid token")

    time_control_equality_conditions = _get_time_control_equality_conditions(challenge.fischer_time_control)

    _perform_common_validations(challenge, caller, session)
    _validate_direct_uniqueness(challenge, caller, session, time_control_equality_conditions)
    callee_online = _validate_direct_callee_returning_online_status(challenge, caller, session)
    _attempt_merging(challenge, caller, session, time_control_equality_conditions)

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
    return ChallengeCreateResponse(result="created", challenge=ChallengePublic.model_validate(db_challenge), callee_online=callee_online)

# TODO: Get challenge

# TODO: Delete (aka. cancel) challenge

# TODO: Get open challenges with pagination

# TODO: Get direct (both incoming and outgoing) challenges + expose for websocket

# TODO: Accept challenge - game starts

# TODO: Decline challenge - notification is sent
