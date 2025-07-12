from datetime import datetime
from enum import auto, StrEnum
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel
from sqlalchemy import CHAR
from sqlmodel import Field, Relationship, SQLModel, Column

from models.column_types import CurrentDatetime
from utils.datatypes import TimeControlKind, UserRestrictionKind, UserRole, UserStatus

if TYPE_CHECKING:
    from .study import Study


class PlayerBase(SQLModel):
    login: str = Field(primary_key=True, max_length=32)
    joined_at: CurrentDatetime
    nickname: str


class Player(PlayerBase, table=True):
    preferred_role: UserRole | None = None  # Don't trust that this role exists! It could have been revoked since then!
    # avatar: bytes | None = Field(sa_column=Column(LargeBinary), default=None)

    password: "PlayerPassword" = Relationship(back_populates="player", cascade_delete=True)
    roles: list["PlayerRole"] = Relationship(back_populates="player", cascade_delete=True)
    restrictions: list["PlayerRestriction"] = Relationship(back_populates="player", cascade_delete=True)
    followed_players: list["PlayerFollowedPlayer"] = Relationship(cascade_delete=True, sa_relationship_kwargs=dict(foreign_keys="PlayerFollowedPlayer.follower_login"))
    studies: list["Study"] = Relationship(back_populates="author", cascade_delete=True)


# <private>
class PlayerPassword(SQLModel, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")
    created_at: CurrentDatetime
    salt: str = Field(sa_column=Column(CHAR(6)))
    password_hash: str = Field(sa_column=Column(CHAR(32)))

    player: Player = Relationship(back_populates="password")


class PlayerRoleBase(SQLModel):
    role: UserRole = Field(primary_key=True)
    granted_at: CurrentDatetime


class PlayerRole(PlayerRoleBase, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")

    player: Player = Relationship(back_populates="roles")


class PlayerRolePublic(PlayerRoleBase):
    is_main: bool


class PlayerRestrictionBase(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    casted_at: CurrentDatetime
    expires: datetime | None = None
    kind: UserRestrictionKind


class PlayerRestriction(PlayerRestrictionBase, table=True):
    login: str = Field(foreign_key="player.login")

    player: Player = Relationship(back_populates="restrictions")


class PlayerRestrictionPublic(PlayerRestrictionBase):
    pass


class PlayerFollowedPlayer(SQLModel, table=True):
    follower_login: str = Field(primary_key=True, foreign_key="player.login")
    followed_login: str = Field(primary_key=True, foreign_key="player.login")
    follows_since: CurrentDatetime


class PlayerEloProgress(SQLModel, table=True):  # Used for: current elo retrieval, elo history plotting, antifraud checks
    id: int | None = Field(default=None, primary_key=True)
    login: str = Field(foreign_key="player.login")
    ts: CurrentDatetime
    time_control_kind: TimeControlKind
    elo: int
    delta: int
    causing_game_id: int = Field(foreign_key="game.id")
    ranked_games_played: int


class GameStats(BaseModel):
    elo: int | None
    is_elo_provisional: bool
    games_cnt: int

    def is_better_than(self, other: Self) -> bool:
        return other.elo is not None and (self.elo is None or self.elo < other.elo)


class PlayerPublic(PlayerBase):
    is_friend: bool
    status: UserStatus
    per_time_control_stats: dict[TimeControlKind, GameStats]
    total_stats: GameStats
    studies_cnt: int
    followed_players: list[str]
    roles: list[PlayerRolePublic]
    restrictions: list[PlayerRestrictionPublic]


class PlayerUpdate(SQLModel):
    nickname: str | None = None
    password: str | None = Field(min_length=6, max_length=128, default=None)
    preferred_role: UserRole | None = None


class RoleOperationPayload(BaseModel):
    role: UserRole


class RestrictionCastingPayload(BaseModel):
    restriction: UserRestrictionKind
    expires: datetime | None = None


class RestrictionRemovalPayload(BaseModel):
    restriction_id: int


class RestrictionBatchRemovalPayload(BaseModel):
    restriction: UserRestrictionKind | None = None
