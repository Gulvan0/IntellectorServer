from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from src.rules.coords import HexCoordinates
from src.rules.piece import Piece, PieceKind


@dataclass
class Ply:
    departure: HexCoordinates
    destination: HexCoordinates
    morph_into: PieceKind | None = None


class PlyKind(Enum):
    NORMAL = auto()
    CAPTURE = auto()
    SWAP = auto()


@dataclass
class DerivedPlyProperties:
    moving_piece: Piece
    target_piece: Piece | None
    ply_kind: PlyKind

    @classmethod
    def from_pieces(cls, moving_piece: Piece, target_piece: Piece | None) -> DerivedPlyProperties:
        if not target_piece:
            ply_kind = PlyKind.NORMAL
        elif target_piece.color == moving_piece.color:
            ply_kind = PlyKind.SWAP
        else:
            ply_kind = PlyKind.CAPTURE
        return DerivedPlyProperties(moving_piece, target_piece, ply_kind)
