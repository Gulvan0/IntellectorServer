from fastapi import HTTPException
from sqlmodel import Session
from src.challenge.datatypes import ChallengeAcceptorColor
from src.challenge.methods.get import get_active_challenge_cnt_by_players, get_identical_challenge, get_total_active_challenges_by_caller
from src.challenge.models import ChallengeCreateDirect, ChallengeCreateOpen

from src.common.user_ref import UserReference
from src.config.models import LimitParams
from src.rules import DEFAULT_STARTING_SIP, Position

import src.player.methods as player_methods
import src.player.models as player_models


def validate_bracket(challenge: ChallengeCreateOpen | ChallengeCreateDirect, session: Session, caller: UserReference) -> None:
    if caller.is_guest() or player_methods.is_banned_in_ranked(session, caller):
        challenge.rated = False


def validate_special_conditions(challenge: ChallengeCreateOpen | ChallengeCreateDirect) -> None:
    if challenge.rated:
        challenge.custom_starting_sip = None
        challenge.acceptor_color = ChallengeAcceptorColor.RANDOM


def validate_startpos(challenge: ChallengeCreateOpen | ChallengeCreateDirect) -> None:
    if challenge.custom_starting_sip:
        if challenge.custom_starting_sip == DEFAULT_STARTING_SIP:
            challenge.custom_starting_sip = None
        elif not Position.from_sip(challenge.custom_starting_sip).is_valid_starting():
            raise HTTPException(status_code=400, detail="Invalid starting situation")


def validate_spam_limits(
    challenge: ChallengeCreateDirect | ChallengeCreateOpen,
    caller: UserReference,
    limits: LimitParams,
    session: Session
):
    total_active_challenges = get_total_active_challenges_by_caller(session, caller)
    max_total = limits.max_total_active_challenges
    if total_active_challenges >= max_total:
        raise HTTPException(status_code=400, detail=f"Too many active challenges (present {total_active_challenges}, max {max_total})")

    if isinstance(challenge, ChallengeCreateDirect):
        same_callee_active_challenges = get_active_challenge_cnt_by_players(session, caller, challenge.callee_ref)
        max_same_callee = limits.max_same_callee_active_challenges
        if total_active_challenges >= max_total:
            raise HTTPException(
                status_code=400,
                detail=f"Too many active direct challenges to {challenge.callee_ref} (present {same_callee_active_challenges}, max {max_same_callee})"
            )


def validate_uniqueness(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: Session
) -> None:
    identical_challenge = get_identical_challenge(session, caller, challenge)
    if identical_challenge:
        raise HTTPException(status_code=400, detail=f"Challenge already exists ({identical_challenge.id})")


def perform_common_validations(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    shutdown_activated: bool,
    limits: LimitParams,
    session: Session
) -> None:
    if shutdown_activated:
        raise HTTPException(status_code=503, detail="Server is preparing to be restarted")
    validate_spam_limits(challenge, caller, limits, session)
    validate_bracket(challenge, session, caller)
    validate_special_conditions(challenge)
    validate_startpos(challenge)
    validate_uniqueness(challenge, caller, session)


def validate_direct_callee(
    challenge: ChallengeCreateDirect,
    caller: UserReference,
    last_guest_id: int,
    session: Session
) -> UserReference:
    if challenge.callee_ref == caller.reference:
        raise HTTPException(status_code=400, detail="Callee and caller cannot be the same user")

    callee = UserReference(challenge.callee_ref)
    if callee.is_guest() and callee.guest_id > last_guest_id:
        raise HTTPException(status_code=404, detail=f"Guest not found: {callee.guest_id}")
    else:
        db_callee = session.get(player_models.Player, callee.login)
        if not db_callee:
            raise HTTPException(status_code=404, detail=f"Player not found: {callee.login}")

    return callee
