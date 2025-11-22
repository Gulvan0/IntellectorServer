from sqlmodel import Field, Relationship

from src.rules import PieceColor
from src.common.field_types import CurrentDatetime
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from src.game.datatypes import OutcomeKind
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GameOutcomeBase(CustomSQLModel):
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
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self) -> "GameEndedBroadcastedData":
        return GameEndedBroadcastedData(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            game_id=self.game_id,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )


class GameOutcomePublic(GameOutcomeBase):
    time_update: GameTimeUpdatePublic | None


class GameEndedBroadcastedData(GameOutcomeBase):
    game_id: int
    time_update: GameTimeUpdatePublic | None
