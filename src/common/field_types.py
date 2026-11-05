from datetime import datetime, UTC
from time import time
from typing import Annotated, Any
from pydantic import StringConstraints
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.mysql import DATETIME
from sqlmodel import Field


PlayerRef = Annotated[str, Field(max_length=32)]
OptionalPlayerRef = Annotated[str | None, Field(default=None, max_length=32)]


def indexed_optional_player_ref() -> Any:
    """OptionalPlayerRef with an index. A function, because `OptionalPlayerRef = Field(index=True)` silently loses the index:
    SQLModel's own Field attributes do not survive the merge with the Annotated one"""
    return Field(default=None, max_length=32, index=True)
Sip = Annotated[str, Field(max_length=127)]
OptionalSip = Annotated[str | None, Field(default=None, max_length=127)]


class UtcDateTime(TypeDecorator[datetime]):
    """Every datetime column's type: stored as naive UTC, aware UTC in the code. A naive value being bound is taken for UTC"""
    impl = DATETIME
    cache_ok = True

    def __init__(self, fsp: int | None = None) -> None:
        self.fsp = fsp
        super().__init__(fsp=fsp)

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.astimezone(UTC).replace(tzinfo=None) if value and value.tzinfo else value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value else None


class PreciseUtcDateTime(UtcDateTime):
    """Keeps the microseconds, which plain DATETIME rounds away. For what clocks are calculated from or rows are ordered by"""
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(fsp=6)


def current_datetime_field(index: bool = False) -> Any:
    """A function rather than an Annotated alias, which would drop sa_type"""
    return Field(default_factory=lambda: datetime.now(UTC), sa_type=UtcDateTime, index=index)


def _require_recorded_datetime() -> datetime:
    raise ValueError("A new row must record this moment; only rows migrated from the old server may pass None")


def legacy_nullable_datetime_field() -> Any:
    """For a `datetime | None` that is null where the moment wasn't recorded (rows migrated from the old server):
    leaving it out fails at construction. The column itself gets no default, as the ORM leaves an explicit None out
    of the INSERT whenever it has one. A function rather than an Annotated alias, which would drop sa_column_kwargs"""
    return Field(default_factory=_require_recorded_datetime, sa_type=PreciseUtcDateTime, sa_column_kwargs={"default": None})


def precise_current_datetime_field(index: bool = False) -> Any:
    """current_datetime_field stored with microseconds. A function for the same reason"""
    return Field(default_factory=lambda: datetime.now(UTC), sa_type=PreciseUtcDateTime, index=index)


CurrentTimestamp = Annotated[int, Field(default_factory=lambda: int(time()))]
PlayerLogin = Annotated[str, StringConstraints(to_lower=True)]
