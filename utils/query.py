from datetime import UTC, datetime

from sqlalchemy import ColumnElement
from sqlmodel import Session, and_, col, or_
from sqlmodel.sql.expression import SelectOfScalar


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


def exists(session: Session, query: SelectOfScalar) -> bool:
    return session.exec(query).first() is not None
