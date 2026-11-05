from datetime import datetime

from sqlalchemy import CHAR
from sqlalchemy.dialects.mysql import TEXT
from sqlmodel import Field, Column

from common.field_types import current_datetime_field, indexed_optional_player_ref, precise_current_datetime_field
from log.datatypes import RestMethod
from utils.custom_model import CustomSQLModel


LOG_SCHEMA = "intellector_logs"


class LogTable(CustomSQLModel):
    """The log tables live in their own database, so that restoring the main one never wipes the recent logs"""
    __table_args__ = {"schema": LOG_SCHEMA}


class ServerLaunch(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    launched_at: datetime = current_datetime_field()


# <private>
class RESTRequestLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = precise_current_datetime_field(index=True)
    client_host: str
    authorized_as: str | None = indexed_optional_player_ref()
    endpoint: str
    method: RestMethod
    headers_json: str = Field(sa_column=Column(TEXT))
    payload: str = Field(sa_column=Column(TEXT))
    response_code: int | None = None  # the request is logged before it is handled, so these stay empty if the server dies meanwhile
    response: str | None = Field(default=None, sa_column=Column(TEXT))


# <private>
class WSLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = precise_current_datetime_field(index=True)
    connection_id: str = Field(sa_column=Column(CHAR(36)))
    authorized_as: str | None = indexed_optional_player_ref()
    payload: str = Field(sa_column=Column(TEXT))
    incoming: bool


# <private>
class ClientErrorLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = precise_current_datetime_field(index=True)
    client_host: str
    authorized_as: str | None = indexed_optional_player_ref()
    build_id: str
    page_path: str = Field(sa_column=Column(TEXT))
    message: str = Field(sa_column=Column(TEXT))
    stack: str | None = Field(default=None, sa_column=Column(TEXT))


# <private>
class TimeoutCheckExecutedLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_time: datetime = current_datetime_field(index=True)
    aborted: bool
    game_id: int
    remaining_ms: int
    is_external: bool


# <private>
class TimeoutCheckPlannedLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_time: datetime = current_datetime_field(index=True)
    game_id: int
    delay_ms: int


# <private>
class TaskFailureLog(LogTable, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = current_datetime_field(index=True)
    task: str
    error: str = Field(sa_column=Column(TEXT))
