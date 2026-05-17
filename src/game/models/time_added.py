from typing import TYPE_CHECKING, Literal
from sqlalchemy.orm import Load, joinedload
from sqlmodel import Field, Relationship

from board.piece import PieceColor
from common.field_types import CurrentDatetime
from game.datatypes import EventKind
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameTimeAddedEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    event_index: int
    amount_seconds: int
    receiver: PieceColor


class GameTimeAddedEvent(GameTimeAddedEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="time_added_events")
    time_update: GameTimeUpdate = Relationship()

    @classmethod
    def load_options(cls) -> list:
        return [
            joinedload(GameTimeAddedEvent.time_update)  # type: ignore[arg-type]
        ]

    def to_public(self) -> GameTimeAddedEventPublic:
        return GameTimeAddedEventPublic(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            amount_seconds=self.amount_seconds,
            receiver=self.receiver,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self) -> TimeAddedBroadcastedData:
        return TimeAddedBroadcastedData(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            amount_seconds=self.amount_seconds,
            receiver=self.receiver,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )


class GameTimeAddedEventPublic(GameTimeAddedEventBase):
    event_kind: Literal[EventKind.TIME_ADDED] = EventKind.TIME_ADDED
    time_update: GameTimeUpdatePublic


class TimeAddedBroadcastedData(GameTimeAddedEventBase):
    time_update: GameTimeUpdatePublic


class GameAddTimePayload(CustomModel):
    game_id: int
    receiver: PieceColor | None = None
