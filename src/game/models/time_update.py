from typing import Optional
from datetime import UTC, datetime
from enum import StrEnum, auto
from sqlmodel import Field, Relationship

from src.rules.piece import PieceColor
from src.game.models.main import Game
from src.utils.custom_model import CustomSQLModel


class GameTimeUpdateReason(StrEnum):
    INIT = auto()
    PLY = auto()
    ROLLBACK = auto()
    TIME_ADDED = auto()
    GAME_ENDED = auto()


class GameTimeUpdateBase(CustomSQLModel):
    updated_at: datetime
    white_ms: int
    black_ms: int
    ticking_side: PieceColor | None
    reason: GameTimeUpdateReason


class GameTimeUpdate(GameTimeUpdateBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    game_id: int | None = Field(default=None, foreign_key="game.id")

    game: Optional["Game"] = Relationship()

    def get_actual_time_remainders(self, reference_ts: datetime | None = None) -> dict[PieceColor, int]:
        remainders = {
            PieceColor.WHITE: self.white_ms,
            PieceColor.BLACK: self.black_ms
        }

        if not self.ticking_side:
            return remainders

        if not reference_ts:
            reference_ts = datetime.now(UTC)

        delta_secs = (reference_ts - self.updated_at).total_seconds()
        delta_ms = int(delta_secs * 1000)
        remainders[self.ticking_side] -= delta_ms

        return remainders


class GameTimeUpdatePublic(GameTimeUpdateBase):
    pass
