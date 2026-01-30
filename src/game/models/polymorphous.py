from typing import Protocol

from board.piece import PieceKind


class PlyPayload(Protocol):
    game_id: int
    original_sip: str | None
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
