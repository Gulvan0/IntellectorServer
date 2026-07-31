from pydantic import Field as PydanticField
from sqlalchemy import CHAR, Column, LargeBinary
from sqlmodel import Field
from common.field_types import CurrentDatetime, PlayerLogin
from common.models import UserRefWithNickname
from utils.custom_model import CustomModel, CustomSQLModel


class AuthCredentials(CustomModel):
    login: str = PydanticField(min_length=2, max_length=32, pattern=r'^[a-zA-Z](_?[a-zA-Z0-9]+)+$')
    password: str = PydanticField(min_length=6, max_length=128)


class TokenResponse(CustomModel):
    token: str
    identity: UserRefWithNickname


class GuestTokenResponse(CustomModel):
    guest_id: int
    token: str


class WhoamiResponse(UserRefWithNickname):
    guest_id: int | None = None


# <private>
class PlayerPassword(CustomSQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    created_at: CurrentDatetime
    password_hash: bytes = Field(sa_column=Column(LargeBinary))
    normal_md5: str | None = None


class PlayerPasswordUpdate(CustomModel):
    login: PlayerLogin
    password: str = PydanticField(min_length=6, max_length=128)
