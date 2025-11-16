from datetime import datetime
from typing import Self

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

from src.common.field_types import CurrentDatetime
from src.player.datatypes import GameStats, UserRestrictionKind, UserRole, UserStatus
from src.common.time_control import TimeControlKind

import src.game.models.main as main_game_models
import src.study.models as study_models


class PlayerBase(SQLModel):
    login: str = Field(primary_key=True, max_length=32)
    joined_at: CurrentDatetime
    nickname: str


class Player(PlayerBase, table=True):
    preferred_role: UserRole | None = None  # Don't trust that this role exists! It could have been revoked since then!
    # avatar: bytes | None = Field(sa_column=Column(LargeBinary), default=None)

    roles: list["PlayerRole"] = Relationship(back_populates="player", cascade_delete=True)
    restrictions: list["PlayerRestriction"] = Relationship(back_populates="player", cascade_delete=True)
    followed_players: list["PlayerFollowedPlayer"] = Relationship(cascade_delete=True, sa_relationship_kwargs=dict(foreign_keys="PlayerFollowedPlayer.follower_login"))
    studies: list[study_models.Study] = Relationship(back_populates="author", cascade_delete=True)


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


class StartedPlayerGamesStateRefresh(BaseModel):
    player_ref: str
    current_game: main_game_models.Game | None
