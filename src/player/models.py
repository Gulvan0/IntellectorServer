from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy.orm import selectinload
from sqlmodel import Field, Relationship

from common.datatypes import UserStatus
from common.field_types import CurrentDatetime, CurrentTimestamp
from common.models import UserActivity, UserRefWithNickname
from player.datatypes import RankedGameStats, UserRestrictionKind, UserRole
from common.time_control import TimeControlKind
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from study.models import Study


class PlayerBase(CustomSQLModel):
    login: str = Field(primary_key=True, max_length=32)
    joined_at: CurrentDatetime
    nickname: str


class Player(PlayerBase, table=True):
    last_ws_activity: CurrentTimestamp
    preferred_role: UserRole | None = None
    # avatar: bytes | None = Field(sa_column=Column(LargeBinary), default=None)

    roles: list[PlayerRole] = Relationship(back_populates="player", cascade_delete=True)
    restrictions: list[PlayerRestriction] = Relationship(back_populates="player", cascade_delete=True)
    followed_players: list[PlayerFollowedPlayer] = Relationship(cascade_delete=True, sa_relationship_kwargs=dict(foreign_keys="PlayerFollowedPlayer.follower_login"))
    studies: list[Study] = Relationship(back_populates="author", cascade_delete=True)

    @classmethod
    def load_options(cls, roles: bool = False, restrictions: bool = False) -> list:
        options = []
        if roles:
            options.append(selectinload(Player.roles))  # type: ignore[arg-type]
        if restrictions:
            options.append(selectinload(Player.restrictions))  # type: ignore[arg-type]
        return options

    def main_role(self) -> UserRole | None:
        main_role = None
        for db_role in self.roles:
            main_role = db_role.role
            if not self.preferred_role or db_role.role == self.preferred_role:
                break
        return main_role

    def to_public(self, activity: UserActivity) -> PlayerPublic:
        return PlayerPublic(
            login=self.login,
            joined_at=self.joined_at,
            nickname=self.nickname,
            main_role=self.main_role(),
            activity=activity,
        )


class PlayerPublic(PlayerBase):
    main_role: UserRole | None = None
    activity: UserActivity


class PlayerRoleBase(CustomSQLModel):
    role: UserRole = Field(primary_key=True)
    granted_at: CurrentDatetime


class PlayerRole(PlayerRoleBase, table=True):
    login: str = Field(primary_key=True, foreign_key="player.login")

    player: Player = Relationship(back_populates="roles")


class PlayerRolePublic(PlayerRoleBase):
    pass


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

    def to_stats(self, calibration_games_cnt: int) -> RankedGameStats:
        return RankedGameStats(
            elo=self.elo,
            is_elo_provisional=self.ranked_games_played < calibration_games_cnt,
            ranked_games_cnt=self.ranked_games_played
        )


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


class PlayerGameStatsByTimeControl(CustomModel):
    elo: int | None = None
    is_elo_provisional: bool = True
    ranked_games_cnt: int = 0
    all_games_cnt: int = 0


class PlayerGameStats(CustomModel):
    by_time_control: dict[TimeControlKind, PlayerGameStatsByTimeControl]
    best_ranked: TimeControlKind | None
    total_count: int


class PlayerRelation(CustomModel):
    you_follow_since: datetime | None = None
    follows_you_since: datetime | None = None


class PlayerMainRating(CustomModel):
    time_control_kind: TimeControlKind
    elo: int
    provisional: bool


class PlayerStatusState(CustomModel):
    status: UserStatus
    last_active_unixsecs: int | None = None  # unknown for a player who hasn't been connected since the server started watching them


class PlayerCard(CustomModel):
    player: UserRefWithNickname
    status: UserStatus
    main_rating: PlayerMainRating | None = None


class PlayerSearchEntry(CustomModel):
    player: UserRefWithNickname
    status: UserStatus
    main_role: UserRole | None = None
    relation: PlayerRelation  # empty for a guest
    main_rating: PlayerMainRating | None = None


class PlayerSearchResult(CustomModel):
    players: list[PlayerSearchEntry]  # best matches first
    total_count: int  # every match, the ones past the limit included


class PlayerConnections(CustomModel):
    friends: list[PlayerCard]  # mutual follows
    following: list[PlayerCard]  # followed by the player, not following them back
    followers: list[PlayerCard]  # following the player, not followed back


class EloHistoryEntry(CustomModel):
    ts: datetime
    elo: int
