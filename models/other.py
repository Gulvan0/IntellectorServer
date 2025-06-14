from enum import auto, StrEnum

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class SavedQuery(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)


class CompatibilityCheckPayload(BaseModel):
    client_build: int
    min_server_build: int


class CompatibilityResolution(StrEnum):
    COMPATIBLE = auto()
    OUTDATED_CLIENT = auto()
    OUTDATED_SERVER = auto()


class CompatibilityResponse(BaseModel):
    resolution: CompatibilityResolution
    server_build: int
    min_client_build: int


class Id(BaseModel):
    id: int
