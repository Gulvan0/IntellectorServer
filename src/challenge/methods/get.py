from typing import Iterable
from sqlmodel import and_, or_, select, func, col

from src.challenge.datatypes import ChallengeKind
from src.challenge.models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen
from src.challenge.sql import time_control_equality_conditions
from src.common.user_ref import UserReference
from src.utils.async_orm_session import AsyncSession


async def get_total_active_challenges_by_caller(session: AsyncSession, caller: UserReference) -> int:
    result = await session.exec(select(
        func.count(col(Challenge.id))
    ).where(
        Challenge.active,
        Challenge.caller_ref == caller.reference
    ))
    return result.one()


async def get_active_challenge_cnt_by_players(session: AsyncSession, caller: UserReference, callee_ref: str) -> int:
    result = await session.exec(select(
        func.count(col(Challenge.id))
    ).where(
        Challenge.active,
        Challenge.caller_ref == caller.reference,
        Challenge.kind == ChallengeKind.DIRECT,
        Challenge.callee_ref == callee_ref
    ))
    return result.one()


async def get_identical_challenge(
    session: AsyncSession,
    caller: UserReference,
    challenge: ChallengeCreateOpen | ChallengeCreateDirect
) -> Challenge | None:
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

    result = await session.exec(
        select(Challenge).where(*conditions)
    )
    return result.first()


async def get_mergeable_challenge(
    session: AsyncSession,
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

    result = await session.exec(query)
    return result.first()


async def get_direct_challenges(
    session: AsyncSession,
    user: UserReference,
    include_incoming: bool = True,
    include_outgoing: bool = True
) -> Iterable[Challenge]:
    assert include_incoming or include_outgoing

    user_filters = []
    if include_incoming:
        user_filters.append(Challenge.callee_ref == user.reference)
    if include_outgoing:
        user_filters.append(Challenge.caller_ref == user.reference)

    result = await session.exec(select(
        Challenge
    ).where(
        Challenge.active == True,  # noqa
        or_(*user_filters)
    ))
    return result.all()
