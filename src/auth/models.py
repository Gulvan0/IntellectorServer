from pydantic import Field as PydanticField
from sqlalchemy import CHAR, Column
from sqlmodel import Field
from src.common.field_types import CurrentDatetime, PlayerLogin
from src.utils.custom_model import CustomModel, CustomSQLModel


class AuthCredentials(CustomModel):
    login: str = PydanticField(min_length=2, max_length=32, pattern=r'^[a-zA-Z](_?[a-zA-Z0-9]+)+$')
    password: str = PydanticField(min_length=6, max_length=128)


class TokenResponse(CustomModel):
    token: str


class GuestTokenResponse(CustomModel):
    guest_id: int
    token: str


# <private>
class PlayerPassword(CustomSQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    created_at: CurrentDatetime
    salt: str = Field(sa_column=Column(CHAR(6)))
    password_hash: str = Field(sa_column=Column(CHAR(32)))


class PlayerPasswordUpdate(CustomModel):
    login: PlayerLogin
    password: str = PydanticField(min_length=6, max_length=128)
