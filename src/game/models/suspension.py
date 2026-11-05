from datetime import datetime
from typing import TYPE_CHECKING, Literal
from sqlalchemy.orm import joinedload
from sqlmodel import Field, Relationship

from common.field_types import legacy_nullable_datetime_field
from game.datatypes import EventKind
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from utils.custom_model import CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameSuspensionEventBase(CustomSQLModel):
    occurred_at: datetime | None = legacy_nullable_datetime_field()
    event_index: int
    suspended: bool


class GameSuspensionEvent(GameSuspensionEventBase, table=True):
    """An external game got suspended because its uploader went silent, or resumed because the uploader returned"""
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="suspension_events")
    time_update: GameTimeUpdate | None = Relationship()

    @classmethod
    def load_options(cls) -> list:
        return [
            joinedload(GameSuspensionEvent.time_update)  # type: ignore[arg-type]
        ]

    def to_public(self) -> GameSuspensionEventPublic:
        return GameSuspensionEventPublic(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            suspended=self.suspended,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )


class GameSuspensionEventPublic(GameSuspensionEventBase):
    event_kind: Literal[EventKind.SUSPENSION] = EventKind.SUSPENSION
    time_update: GameTimeUpdatePublic | None  # the bot's clock frozen or restarted by the change; none if no clock was affected
