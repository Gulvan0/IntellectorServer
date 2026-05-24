from sqlmodel import and_, desc, or_, select, func, col
from sqlmodel.sql.expression import SelectOfScalar

from challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from challenge.models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengePublic
from challenge.sql import time_control_equality_conditions
from common.user_ref import UserReference
from player.methods import resolve_player_refs
from utils.async_orm_session import AsyncSession


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
        or_(
            Challenge.acceptor_color == ChallengeAcceptorColor.RANDOM,
            challenge.acceptor_color == ChallengeAcceptorColor.RANDOM,
            Challenge.acceptor_color != challenge.acceptor_color
        ),
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


async def _query_challenges_as_public(session: AsyncSession, query: SelectOfScalar[Challenge]) -> list[ChallengePublic]:
    result = list(await session.exec(query.options(
        *Challenge.load_options()
    )))

    collected_refs = set()
    for db_challenge in result:
        collected_refs |= db_challenge.collect_refs(include_nested=True)

    resolved_refs = await resolve_player_refs(collected_refs, session)

    return [
        db_challenge.to_public(resolved_refs)
        for db_challenge in result
    ]


async def get_direct_challenges(
    session: AsyncSession,
    user: UserReference,
    include_incoming: bool = True,
    include_outgoing: bool = True
) -> list[ChallengePublic]:
    user_filters = []
    if include_incoming:
        user_filters.append(Challenge.callee_ref == user.reference)
    if include_outgoing:
        user_filters.append(Challenge.caller_ref == user.reference)
    if not user_filters:
        raise ValueError('Either include_incoming or include_outgoing should be True')

    return await _query_challenges_as_public(session, select(
        Challenge
    ).where(
        Challenge.active == True,  # noqa
        or_(*user_filters)
    ).order_by(
        desc(Challenge.created_at)
    ))


async def get_active_public_challenges(session: AsyncSession, offset: int = 0, limit: int = 50) -> list[ChallengePublic]:
    return await _query_challenges_as_public(session, select(
        Challenge
    ).where(
        Challenge.active == True,  # noqa
        Challenge.kind == ChallengeKind.PUBLIC,
    ).offset(
        offset
    ).limit(
        limit
    ).order_by(
        desc(Challenge.created_at)
    ))
