from sqlmodel import Field, Relationship, SQLModel

from src.rules import PieceColor
from src.utils.cast import model_cast
from src.common.field_types import CurrentDatetime
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic

import src.game.models.main as game_main_models


class GameTimeAddedEventBase(SQLModel):
    occurred_at: CurrentDatetime
    amount_seconds: int
    receiver: PieceColor


class GameTimeAddedEvent(GameTimeAddedEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: game_main_models.Game = Relationship(back_populates="time_added_events")
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
