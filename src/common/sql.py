from datetime import UTC, datetime

from sqlalchemy import ColumnElement
from sqlmodel import Session, and_, col, or_, func, case
from sqlmodel.sql.expression import SelectOfScalar

from src.utils.async_orm_session import AsyncSession


def not_expired(expiration_dt: datetime | None) -> ColumnElement[bool]:
    return or_(
        expiration_dt == None,
        col(expiration_dt) > datetime.now(UTC)
    )


def expired(expiration_dt: datetime | None) -> ColumnElement[bool]:
    return and_(
        expiration_dt != None,
        col(expiration_dt) <= datetime.now(UTC)
    )


def count_if(condition):
    return func.sum(case((condition, 1), else_=0))


async def exists(session: AsyncSession, query: SelectOfScalar) -> bool:
    result = await session.exec(query)
    return result.first() is not None
