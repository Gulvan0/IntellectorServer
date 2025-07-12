from typing import Optional
from sqlalchemy import CHAR
from sqlmodel import Field, Relationship, SQLModel, Column

from .column_types import CurrentDatetime, OptionalPlayerRef


class ServerLaunch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    launched_at: CurrentDatetime


# <private>
class RESTRequestLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    client_host: str
    authorized_as: OptionalPlayerRef
    endpoint: str
    method: str = Field(sa_column=Column(CHAR(5)))
    headers_json: str
    payload: str

    response: Optional["RESTResponseLog"] = Relationship(back_populates="request")


# <private>
class RESTResponseLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="restrequestlog.id")
    response_code: int
    response: str

    request: RESTRequestLog = Relationship(back_populates="response")


# <private>
class WSLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    connection_id: str = Field(sa_column=Column(CHAR(32)))
    authorized_as: OptionalPlayerRef
    payload_json: str
    incoming: bool


# <private>
class ServiceLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    service: str
    message: str
