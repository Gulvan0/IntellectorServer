from typing import Optional
from sqlalchemy import CHAR
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlmodel import Field, Relationship, Column

from src.common.field_types import CurrentDatetime, OptionalPlayerRef
from src.utils.custom_model import CustomSQLModel


class ServerLaunch(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    launched_at: CurrentDatetime


# <private>
class RESTRequestLog(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    client_host: str
    authorized_as: OptionalPlayerRef
    endpoint: str
    method: str = Field(sa_column=Column(CHAR(5)))
    headers_json: str = Field(sa_column=Column(MEDIUMTEXT))
    payload: str

    response: Optional["RESTResponseLog"] = Relationship(back_populates="request")


# <private>
class RESTResponseLog(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="restrequestlog.id")
    response_code: int
    response: str

    request: RESTRequestLog = Relationship(back_populates="response")


# <private>
class WSLog(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    connection_id: str = Field(sa_column=Column(CHAR(36)))
    authorized_as: OptionalPlayerRef
    payload: str
    incoming: bool


# <private>
class ServiceLog(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: CurrentDatetime
    service: str
    message: str
