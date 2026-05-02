from dataclasses import dataclass, field
from enum import auto, StrEnum
from typing import Self

from common.time_control import TimeControlKind
from utils.custom_model import CustomModel


class UserRole(StrEnum):
    ADMIN = auto()
    ANACONDA_DEVELOPER = auto()


class UserRestrictionKind(StrEnum):
    RATED_GAMES = auto()
    SET_AVATAR = auto()
    CHAT = auto()


class RankedGameStats(CustomModel):
    elo: int | None = None
    is_elo_provisional: bool = True
    ranked_games_cnt: int = 0

    def is_better_than(self, other: Self) -> bool:
        if self.elo is None:
            return False
        if other.elo is None:
            return True

        raw_better = self.elo > other.elo or self.elo == other.elo and self.ranked_games_cnt > other.ranked_games_cnt
        if self.is_elo_provisional:
            return other.is_elo_provisional and raw_better
        return other.is_elo_provisional or raw_better


@dataclass
class OverallRankedGameStats:
    by_time_control: dict[TimeControlKind, RankedGameStats] = field(default_factory=dict)
    best: TimeControlKind | None = None

    def extend_with(self, time_control_kind: TimeControlKind, stats: RankedGameStats) -> None:
        if time_control_kind in self.by_time_control:
            return

        self.by_time_control[time_control_kind] = stats

        if self.best:
            if stats.is_better_than(self.by_time_control[self.best]):
                self.best = time_control_kind
        else:
            if stats.elo is not None:
                self.best = time_control_kind
