from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import CHAR, Column
from sqlmodel import Field, SQLModel
from src.common.field_types import CurrentDatetime, PlayerLogin


class AuthCredentials(BaseModel):
    login: str = PydanticField(min_length=2, max_length=32, pattern=r'^[a-zA-Z](_?[a-zA-Z0-9]+)+$')
    password: str = PydanticField(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    token: str


class GuestTokenResponse(BaseModel):
    guest_id: int
    token: str


# <private>
class PlayerPassword(SQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    created_at: CurrentDatetime
    salt: str = Field(sa_column=Column(CHAR(6)))
    password_hash: str = Field(sa_column=Column(CHAR(32)))


class PlayerPasswordUpdate(BaseModel):
    login: PlayerLogin
    password: str = PydanticField(min_length=6, max_length=128)
