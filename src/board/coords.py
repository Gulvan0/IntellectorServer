from dataclasses import dataclass
from typing import assert_never

from board.constants.common import BOARD_HEX_COUNT
from board.piece import PieceColor
from board.piece_movement import PieceMovementDirection


@dataclass(frozen=True)
class HexCoordinates:
    i: int
    j: int

    @classmethod
    def from_scalar(cls, scalar: int) -> HexCoordinates:
        i = scalar % 9 * 2
        if i > 8:
            i -= 9
        return HexCoordinates(i, scalar // 9)

    def __hash__(self) -> int:
        return self.scalar

    @property
    def scalar(self) -> int:
        base = 9 * self.j + self.i // 2
        if self.i % 2:
            return base + 5
        return base

    def is_valid(self) -> bool:
        if self.j == 6:
            return self.i % 2 == 0 and 0 <= self.i < 9
        return 0 <= self.j < 6 and 0 <= self.i < 9

    def is_final_row_for(self, side: PieceColor) -> bool:
        if side == PieceColor.WHITE:
            return self.scalar < 5
        else:
            return BOARD_HEX_COUNT - 5 <= self.scalar

    def is_lateral_neighbour_for(self, other: HexCoordinates) -> bool:
        delta_i = self.i - other.i
        delta_j = self.j - other.j
        allowed_j_offset_on_sides = -1 if other.i % 2 == 0 else 1
        if delta_i == 0:
            return delta_j in (-1, 1)
        else:
            return delta_i in (-1, 1) and delta_j in (0, allowed_j_offset_on_sides)

    def step(self, direction: PieceMovementDirection, color: PieceColor = PieceColor.WHITE, distance: int = 1) -> HexCoordinates | None:
        # black's directions are white's turned around; the column-parity terms below only hold for white's
        if color == PieceColor.BLACK:
            return self.step(direction.opposite(), PieceColor.WHITE, distance)
        match direction:
            case PieceMovementDirection.FORWARD:
                next_hex = HexCoordinates(self.i, self.j - distance)
            case PieceMovementDirection.FORWARD_LEFT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i - distance, self.j - (distance + addend) // 2)
            case PieceMovementDirection.FORWARD_RIGHT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i + distance, self.j - (distance + addend) // 2)
            case PieceMovementDirection.BACK:
                next_hex = HexCoordinates(self.i, self.j + distance)
            case PieceMovementDirection.BACK_LEFT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i - distance, self.j + (distance + addend) // 2)
            case PieceMovementDirection.BACK_RIGHT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i + distance, self.j + (distance + addend) // 2)
            case PieceMovementDirection.AGR_LEFT:
                next_hex = HexCoordinates(self.i - 2 * distance, self.j)
            case PieceMovementDirection.AGR_RIGHT:
                next_hex = HexCoordinates(self.i + 2 * distance, self.j)
            case PieceMovementDirection.AGR_BACK_LEFT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i - distance, self.j + ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_BACK_RIGHT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i + distance, self.j + ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_FORWARD_LEFT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i - distance, self.j - ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_FORWARD_RIGHT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i + distance, self.j - ((distance + addend) // 2 + distance))
            case _:
                assert_never(direction)
        return next_hex if next_hex.is_valid() else None
