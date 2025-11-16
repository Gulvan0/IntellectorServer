from typing import Iterable
from sqlalchemy import ColumnElement
from sqlmodel import Session, and_, or_, select, func, col

from src.challenge.datatypes import ChallengeKind
from src.challenge.models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen
from src.challenge.sql import time_control_equality_conditions
from src.common.user_ref import UserReference


def get_total_active_challenges_by_caller(session: Session, caller: UserReference) -> int:
    return session.exec(select(
        func.count(col(Challenge.id))
    ).where(
        Challenge.active,
        Challenge.caller_ref == caller.reference
    )).one()


def get_active_challenge_cnt_by_players(session: Session, caller: UserReference, callee_ref: str) -> int:
    return session.exec(select(
        func.count(col(Challenge.id))
    ).where(
        Challenge.active,
        Challenge.caller_ref == caller.reference,
        Challenge.kind == ChallengeKind.DIRECT,
        Challenge.callee_ref == callee_ref
    )).one()


def get_identical_challenge(session: Session, caller: UserReference, challenge: ChallengeCreateOpen | ChallengeCreateDirect) -> Challenge | None:
    conditions = [
        Challenge.active,
        Challenge.acceptor_color == challenge.acceptor_color,
        Challenge.caller_ref == caller.reference,
        Challenge.rated == challenge.rated,
        Challenge.custom_starting_sip == challenge.custom_starting_sip,
    ] + time_control_equality_conditions(challenge.fischer_time_control)
    if isinstance(challenge, ChallengeCreateDirect):
        conditions += [
            Challenge.kind == ChallengeKind.DIRECT,
            Challenge.callee_ref == challenge.callee_ref,
        ]
    return session.exec(
        select(Challenge).where(*conditions)
    ).first()


def get_mergeable_challenge(
    session: Session,
    caller: UserReference,
    challenge: ChallengeCreateOpen | ChallengeCreateDirect
) -> Challenge | None:
    if isinstance(challenge, ChallengeCreateOpen) and challenge.link_only:
        return None

    conditions = [
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
    ] + time_control_equality_conditions(challenge.fischer_time_control)
    if isinstance(challenge, ChallengeCreateDirect):
        conditions.append(Challenge.caller_ref == challenge.callee_ref)

    query = select(
        Challenge
    ).where(
        *conditions  # type: ignore
    ).order_by(
        col(Challenge.created_at)
    )

    return session.exec(query).first()


async def get_direct_challenges(session: Session, user: UserReference, include_incoming: bool = True, include_outgoing: bool = True) -> Iterable[Challenge]:
    assert include_incoming or include_outgoing

    user_filters = []
    if include_incoming:
        user_filters.append(Challenge.callee_ref == user.reference)
    if include_outgoing:
        user_filters.append(Challenge.caller_ref == user.reference)

    return session.exec(select(
        Challenge
    ).where(
        Challenge.active == True,  # noqa
        or_(*user_filters)
    )).all()
