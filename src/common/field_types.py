from datetime import datetime, UTC
from time import time
from typing import Annotated, Any
from pydantic import StringConstraints
from sqlmodel import Field


PlayerRef = Annotated[str, Field(max_length=32)]
OptionalPlayerRef = Annotated[str | None, Field(default=None, max_length=32)]
Sip = Annotated[str, Field(max_length=127)]
OptionalSip = Annotated[str | None, Field(default=None, max_length=127)]
CurrentDatetime = Annotated[datetime, Field(default_factory=lambda: datetime.now(UTC))]


def _require_recorded_datetime() -> datetime:
    raise ValueError("A new row must record this moment; only rows migrated from the old server may pass None")


def legacy_nullable_datetime_field() -> Any:
    """For a `datetime | None` that is null where the moment wasn't recorded (rows migrated from the old server):
    leaving it out fails at construction. The column itself gets no default, as the ORM leaves an explicit None out
    of the INSERT whenever it has one. A function rather than an Annotated alias, which would drop sa_column_kwargs"""
    return Field(default_factory=_require_recorded_datetime, sa_column_kwargs={"default": None})
CurrentTimestamp = Annotated[int, Field(default_factory=lambda: int(time()))]
PlayerLogin = Annotated[str, StringConstraints(to_lower=True)]
