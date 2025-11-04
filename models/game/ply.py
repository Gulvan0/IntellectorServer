from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from rules import PieceColor, PieceKind, PlyKind

from ..column_types import CurrentDatetime, Sip


if TYPE_CHECKING:
    from .main import Game
    from .time_update import GameTimeUpdate, GameTimeUpdatePublic


class GamePlyEventBase(SQLModel):
    occurred_at: CurrentDatetime
    ply_index: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None


class GamePlyEvent(GamePlyEventBase, table=True):  # Analytics-optimized
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    is_cancelled: bool = False
    kind: PlyKind
    moving_color: PieceColor
    moved_piece: PieceKind
    target_piece: PieceKind | None = None
    sip_after: Sip
    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="ply_events")
    time_update: GameTimeUpdate | None = Relationship()


class GamePlyEventPublic(GamePlyEventBase):
    time_update: GameTimeUpdatePublic | None
    is_cancelled: bool = False


class PlyBroadcastedData(GamePlyEventBase):
    game_id: int
    sip_after: Sip
    time_update: GameTimeUpdatePublic | None
