from sqlmodel import Field, Relationship, SQLModel

from src.rules import PieceColor
from src.common.field_types import CurrentDatetime
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from src.game.datatypes import OutcomeKind
from src.utils.cast import model_cast_optional

import src.game.models.main as game_main_models


class GameOutcomeBase(SQLModel):
    game_ended_at: CurrentDatetime
    kind: OutcomeKind
    winner: PieceColor | None = None


class GameOutcome(GameOutcomeBase, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: game_main_models.Game = Relationship(back_populates="outcome")
    time_update: GameTimeUpdate | None = Relationship()

    def to_public(self) -> "GameOutcomePublic":
        return GameOutcomePublic(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            time_update=model_cast_optional(self.time_update, GameTimeUpdatePublic)
        )

    def to_broadcasted_data(self) -> "GameEndedBroadcastedData":
        return GameEndedBroadcastedData(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            game_id=self.game_id,
            time_update=model_cast_optional(self.time_update, GameTimeUpdatePublic)
        )


class GameOutcomePublic(GameOutcomeBase):
    time_update: GameTimeUpdatePublic | None


class GameEndedBroadcastedData(GameOutcomeBase):
    game_id: int
    time_update: GameTimeUpdatePublic | None
