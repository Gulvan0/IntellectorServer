from datetime import datetime

from sqlalchemy import CHAR 
from sqlmodel import Field, SQLModel, Column

from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN


class ServerLaunch(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    launched_at: datetime = CURRENT_DATETIME_COLUMN


# <private>
class RESTLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: datetime = CURRENT_DATETIME_COLUMN
    client_host: str
    authorized_as: str | None = PLAYER_REF_COLUMN
    endpoint: str
    method: str = Field(sa_column=Column(CHAR(4)))
    headers_json: str
    payload_json: str
    response_code: int
    response_json: str


# <private>
class WSLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: datetime = CURRENT_DATETIME_COLUMN
    connection_id: str = Field(sa_column=Column(CHAR(32)))
    authorized_as: str | None = PLAYER_REF_COLUMN
    payload_json: str
    incoming: bool


# <private>
class ServiceLog(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    ts: datetime = CURRENT_DATETIME_COLUMN
    service: str
    message: str