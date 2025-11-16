from dataclasses import dataclass, field
from enum import auto, StrEnum

from src.common.time_control import TimeControlKind


class OutcomeKind(StrEnum):
    FATUM = auto()
    BREAKTHROUGH = auto()
    TIMEOUT = auto()
    RESIGN = auto()
    ABANDON = auto()
    DRAW_AGREEMENT = auto()
    REPETITION = auto()
    NO_PROGRESS = auto()
    ABORT = auto()


class OfferKind(StrEnum):
    DRAW = auto()
    TAKEBACK = auto()


class OfferAction(StrEnum):
    CREATE = auto()
    CANCEL = auto()
    ACCEPT = auto()
    DECLINE = auto()


@dataclass
class OverallGameCounts:
    by_time_control: dict[TimeControlKind, int] = field(default_factory=dict)
    total: int = 0
