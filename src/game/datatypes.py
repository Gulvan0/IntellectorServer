from dataclasses import dataclass, field
from enum import auto, StrEnum

from src.common.time_control import TimeControlKind
from src.rules import PieceColor
from src.utils.custom_model import CustomModel


class TimeRemainders(CustomModel):
    white_ms: int
    black_ms: int


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

    @property
    def drawish(self) -> bool:
        return self in (OutcomeKind.DRAW_AGREEMENT, OutcomeKind.REPETITION, OutcomeKind.NO_PROGRESS, OutcomeKind.ABORT)


class SimpleOutcome(CustomModel):
    kind: OutcomeKind
    winner: PieceColor | None = None


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
