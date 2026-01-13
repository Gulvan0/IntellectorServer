from __future__ import annotations

from dataclasses import dataclass
from enum import auto, StrEnum

from src.rules.piece_movement import PieceMovementDirection, PieceMovementRule, UnlimitedPieceMovementDistance


class PieceKind(StrEnum):
    PROGRESSOR = auto()
    AGGRESSOR = auto()
    DEFENSOR = auto()
    LIBERATOR = auto()
    DOMINATOR = auto()
    INTELLECTOR = auto()

    @classmethod
    def promotion_options(cls) -> list[PieceKind]:
        return [
            PieceKind.AGGRESSOR,
            PieceKind.DEFENSOR,
            PieceKind.LIBERATOR,
            PieceKind.DOMINATOR,
        ]

    @classmethod
    def affected_by_aura(cls) -> list[PieceKind]:
        return [
            PieceKind.AGGRESSOR,
            PieceKind.DEFENSOR,
            PieceKind.LIBERATOR,
            PieceKind.DOMINATOR,
        ]

    def get_movement_rules(self) -> list[PieceMovementRule]:
        match self:
            case PieceKind.PROGRESSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.forward_lateral_directions(),
                        allowed_distances=[1]
                    )
                ]
            case PieceKind.AGGRESSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.radial_directions(),
                        allowed_distances=UnlimitedPieceMovementDistance()
                    )
                ]
            case PieceKind.DEFENSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        swappable_with=[PieceKind.INTELLECTOR]
                    )
                ]
            case PieceKind.LIBERATOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        can_capture=False
                    ),
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[2],
                        can_jump=True
                    )
                ]
            case PieceKind.DOMINATOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=UnlimitedPieceMovementDistance()
                    )
                ]
            case PieceKind.INTELLECTOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        swappable_with=[PieceKind.DEFENSOR]
                    )
                ]


class PieceColor(StrEnum):
    WHITE = auto()
    BLACK = auto()

    def opposite(self) -> PieceColor:
        return PieceColor.BLACK if self == PieceColor.WHITE else PieceColor.WHITE


@dataclass(frozen=True)
class Piece:
    kind: PieceKind
    color: PieceColor
