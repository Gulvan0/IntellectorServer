from pydantic import Field as PydanticField
from sqlalchemy import Column, LargeBinary
from sqlmodel import Field
from datetime import datetime

from common.constants import DbSchema
from common.field_types import PlayerLogin, current_datetime_field
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


class PlayerPassword(CustomSQLModel, table=True):
    """In the sensitive database, which the read-only search user has no access to. Every table holding secrets belongs there.
    No foreign key to `player`: either database can be restored without the other"""
    __table_args__ = {"schema": DbSchema.SENSITIVE}

    login: str = Field(primary_key=True)
    created_at: datetime = current_datetime_field()
    password_hash: bytes = Field(sa_column=Column(LargeBinary))
    normal_md5: str | None = None


class PlayerPasswordUpdate(CustomModel):
    login: PlayerLogin
    password: str = PydanticField(min_length=6, max_length=128)
