from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from rules import PieceColor
from utils.query import model_cast

from ..column_types import CurrentDatetime


if TYPE_CHECKING:
    from .main import Game
    from .time_update import GameTimeUpdate, GameTimeUpdatePublic


class GameTimeAddedEventBase(SQLModel):
    occurred_at: CurrentDatetime
    amount_seconds: int
    receiver: PieceColor


class GameTimeAddedEvent(GameTimeAddedEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="ply_events")
    time_update: GameTimeUpdate = Relationship()

    def to_public(self) -> "GameTimeAddedEventPublic":
        return GameTimeAddedEventPublic(
            occurred_at=self.occurred_at,
            amount_seconds=self.amount_seconds,
            receiver=self.receiver,
            time_update=model_cast(self.time_update, GameTimeUpdatePublic)
        )

    def to_broadcasted_data(self) -> "TimeAddedBroadcastedData":
        return TimeAddedBroadcastedData(
            occurred_at=self.occurred_at,
            amount_seconds=self.amount_seconds,
            receiver=self.receiver,
            game_id=self.game_id,
            time_update=model_cast(self.time_update, GameTimeUpdatePublic)
        )


class GameTimeAddedEventPublic(GameTimeAddedEventBase):
    time_update: GameTimeUpdatePublic


class TimeAddedBroadcastedData(GameTimeAddedEventBase):
    game_id: int
    time_update: GameTimeUpdatePublic
