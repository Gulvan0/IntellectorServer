from datetime import datetime
from sqlmodel import Field, Relationship

from src.common.field_types import CurrentDatetime
from src.player.datatypes import GameStats, UserRestrictionKind, UserRole, UserStatus
from src.common.time_control import TimeControlKind
from src.utils.custom_model import CustomModel, CustomSQLModel

import src.game.models.main as main_game_models
import src.study.models as study_models


class PlayerBase(CustomSQLModel):
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


class PlayerRoleBase(CustomSQLModel):
    role: UserRole = Field(primary_key=True)
    granted_at: CurrentDatetime


class PlayerRole(PlayerRoleBase, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")

    player: Player = Relationship(back_populates="roles")


class PlayerRolePublic(PlayerRoleBase):
    is_main: bool


class PlayerRestrictionBase(CustomSQLModel):
    id: int | None = Field(default=None, primary_key=True)
    casted_at: CurrentDatetime
    expires: datetime | None = None
    kind: UserRestrictionKind


class PlayerRestriction(PlayerRestrictionBase, table=True):
    login: str = Field(foreign_key="player.login")

    player: Player = Relationship(back_populates="restrictions")


class PlayerRestrictionPublic(PlayerRestrictionBase):
    pass


class PlayerFollowedPlayer(CustomSQLModel, table=True):
    follower_login: str = Field(primary_key=True, foreign_key="player.login")
    followed_login: str = Field(primary_key=True, foreign_key="player.login")
    follows_since: CurrentDatetime


class PlayerEloProgress(CustomSQLModel, table=True):  # Used for: current elo retrieval, elo history plotting, antifraud checks
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


class PlayerUpdate(CustomSQLModel):
    nickname: str | None = None
    preferred_role: UserRole | None = None


class RoleOperationPayload(CustomModel):
    role: UserRole


class RestrictionCastingPayload(CustomModel):
    restriction: UserRestrictionKind
    expires: datetime | None = None


class RestrictionRemovalPayload(CustomModel):
    restriction_id: int


class RestrictionBatchRemovalPayload(CustomModel):
    restriction: UserRestrictionKind | None = None


class StartedPlayerGamesStateRefresh(CustomModel):
    player_ref: str
    current_game: main_game_models.Game | None
