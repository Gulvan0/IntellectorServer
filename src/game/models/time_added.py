from sqlmodel import Field, Relationship

from src.rules.piece import PieceColor
from src.common.field_types import CurrentDatetime
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GameTimeAddedEventBase(CustomSQLModel):
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
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self) -> "TimeAddedBroadcastedData":
        return TimeAddedBroadcastedData(
            occurred_at=self.occurred_at,
            amount_seconds=self.amount_seconds,
            receiver=self.receiver,
            game_id=self.game_id,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )


class GameTimeAddedEventPublic(GameTimeAddedEventBase):
    time_update: GameTimeUpdatePublic


class TimeAddedBroadcastedData(GameTimeAddedEventBase):
    game_id: int
    time_update: GameTimeUpdatePublic
