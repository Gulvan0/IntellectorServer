from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlmodel import Session, and_, col, or_, func, case
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


def count_if(condition):
    return func.sum(case((condition, 1), else_=0))


def model_cast_optional[TargetModelType: BaseModel](source: BaseModel | None, target: type[TargetModelType]) -> TargetModelType | None:
    return target.model_construct(**source.model_dump()) if source else None


def model_cast[TargetModelType: BaseModel](source: BaseModel, target: type[TargetModelType]) -> TargetModelType:
    return target.model_construct(**source.model_dump())
