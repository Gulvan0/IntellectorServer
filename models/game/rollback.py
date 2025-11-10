from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from rules import PieceColor
from utils.query import model_cast_optional

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

    def to_public(self) -> "GameRollbackEventPublic":
        return GameRollbackEventPublic(
            occurred_at=self.occurred_at,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=model_cast_optional(self.time_update, GameTimeUpdatePublic)
        )

    def to_broadcasted_data(self, updated_sip: str) -> "RollbackBroadcastedData":
        return RollbackBroadcastedData(
            occurred_at=self.occurred_at,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=model_cast_optional(self.time_update, GameTimeUpdatePublic),
            game_id=self.game_id,
            updated_sip=updated_sip
        )


class GameRollbackEventPublic(GameRollbackEventBase):
    time_update: GameTimeUpdatePublic | None


class RollbackBroadcastedData(GameRollbackEventBase):
    game_id: int
    time_update: GameTimeUpdatePublic | None
    updated_sip: Sip
