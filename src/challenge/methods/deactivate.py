from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlmodel import col

from challenge.models import Challenge
from utils.async_orm_session import AsyncSession


async def deactivate_challenge(challenge_id: int, session: AsyncSession) -> bool:
    """Of the actions ending a challenge at once (accepting, merging, declining, cancelling), only one gets True, and
    only that one may go on. The row stays locked until its transaction ends, so the rest wait to see how it went:
    if it rolls back, the challenge is still active for them"""
    statement = update(Challenge).where(col(Challenge.id) == challenge_id, col(Challenge.active) == True).values(active=False)  # noqa: E712
    result = cast("CursorResult[Any]", await session.exec(statement))  # type: ignore[call-overload]
    return result.rowcount == 1
