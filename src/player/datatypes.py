from dataclasses import dataclass, field
from enum import auto, StrEnum
from typing import Self

from src.common.time_control import TimeControlKind
from src.utils.custom_model import CustomModel


class UserRole(StrEnum):
    ADMIN = auto()
    ANACONDA_DEVELOPER = auto()


class UserRestrictionKind(StrEnum):
    RATED_GAMES = auto()
    SET_AVATAR = auto()
    CHAT = auto()


class UserStatus(StrEnum):
    ONLINE = auto()
    AWAY = auto()
    OFFLINE = auto()

    def is_more_active_than(self, other: Self) -> bool:
        match other:
            case UserStatus.AWAY:
                return self == UserStatus.ONLINE
            case UserStatus.OFFLINE:
                return self != UserStatus.OFFLINE
            case _:
                return False


class GameStats(CustomModel):
    elo: int | None
    is_elo_provisional: bool
    games_cnt: int

    def is_better_than(self, other: Self) -> bool:
        return other.elo is not None and (self.elo is None or self.elo < other.elo)


@dataclass
class OverallGameStats:
    by_time_control: dict[TimeControlKind, GameStats] = field(default_factory=dict)
    best: GameStats = field(default_factory=lambda: GameStats(elo=None, is_elo_provisional=True, games_cnt=0))

    def extend_with(self, time_control_kind: TimeControlKind, stats: GameStats) -> None:
        if time_control_kind in self.by_time_control:
            return
        self.by_time_control[time_control_kind] = stats
        if stats.is_better_than(self.best):
            self.best = stats
