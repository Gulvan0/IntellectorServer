from __future__ import annotations

from dataclasses import dataclass, field
from enum import auto, Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from src.rules.piece import PieceKind


class PieceMovementDirection(Enum):
    FORWARD = auto()
    FORWARD_LEFT = auto()
    FORWARD_RIGHT = auto()
    BACK = auto()
    BACK_LEFT = auto()
    BACK_RIGHT = auto()
    AGR_FORWARD_LEFT = auto()
    AGR_FORWARD_RIGHT = auto()
    AGR_BACK_LEFT = auto()
    AGR_BACK_RIGHT = auto()
    AGR_LEFT = auto()
    AGR_RIGHT = auto()

    @classmethod
    def forward_lateral_directions(cls) -> list[PieceMovementDirection]:
        return [cls.FORWARD, cls.FORWARD_LEFT, cls.FORWARD_RIGHT]

    @classmethod
    def backward_lateral_directions(cls) -> list[PieceMovementDirection]:
        return [cls.BACK, cls.BACK_LEFT, cls.BACK_RIGHT]

    @classmethod
    def lateral_directions(cls) -> list[PieceMovementDirection]:
        return cls.forward_lateral_directions() + cls.backward_lateral_directions()

    @classmethod
    def radial_directions(cls) -> list[PieceMovementDirection]:
        return [cls.AGR_FORWARD_LEFT, cls.AGR_FORWARD_RIGHT, cls.AGR_BACK_LEFT, cls.AGR_BACK_RIGHT, cls.AGR_LEFT, cls.AGR_RIGHT]


class UnlimitedPieceMovementDistance:
    pass


@dataclass
class PieceMovementRule:
    allowed_directions: list[PieceMovementDirection]
    allowed_distances: list[int] | UnlimitedPieceMovementDistance
    can_capture: bool = True
    can_jump: bool = False
    swappable_with: list["PieceKind"] = field(default_factory=list)
