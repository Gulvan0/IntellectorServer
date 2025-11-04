from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from rules import PieceColor

from ..column_types import CurrentDatetime, Sip


if TYPE_CHECKING:
    from .main import Game
    from .time_update import GameTimeUpdate, GameTimeUpdatePublic


class GameRollbackEventBase(SQLModel):
    occurred_at: CurrentDatetime
    ply_cnt_before: int
    ply_cnt_after: int
    requested_by: PieceColor


class GameRollbackEvent(GameRollbackEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="ply_events")
    time_update: GameTimeUpdate | None = Relationship()


class GameRollbackEventPublic(GameRollbackEventBase):
    time_update: GameTimeUpdatePublic | None


class RollbackBroadcastedData(GameRollbackEventBase):
    game_id: int
    time_update: GameTimeUpdatePublic | None
    updated_sip: Sip
