from sqlalchemy import CHAR
from sqlmodel import Field, SQLModel, Column

from .column_types import CurrentDatetime, OptionalPlayerRef


class ServerLaunch(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    launched_at: CurrentDatetime


# <private>
class RESTLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: CurrentDatetime
    client_host: str
    authorized_as: OptionalPlayerRef
    endpoint: str
    method: str = Field(sa_column=Column(CHAR(4)))
    headers_json: str
    payload_json: str
    response_code: int
    response_json: str


# <private>
class WSLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: CurrentDatetime
    connection_id: str = Field(sa_column=Column(CHAR(32)))
    authorized_as: OptionalPlayerRef
    payload_json: str
    incoming: bool


# <private>
class ServiceLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: CurrentDatetime
    service: str
    message: str
