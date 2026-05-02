from typing import TYPE_CHECKING
from sqlalchemy.orm import Load, joinedload
from sqlmodel import Field, Relationship

from board.piece import PieceColor
from common.field_types import CurrentDatetime
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from game.datatypes import OutcomeKind
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameOutcomeBase(CustomSQLModel):
    game_ended_at: CurrentDatetime
    kind: OutcomeKind
    winner: PieceColor | None = None


class GameEndedEloUpdate(CustomModel):
    new_value: int
    delta: int


class GameEndedEloUpdates(CustomModel):
    white: GameEndedEloUpdate
    black: GameEndedEloUpdate


class GameOutcome(GameOutcomeBase, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="outcome")
    time_update: GameTimeUpdate | None = Relationship()

    @classmethod
    def load_options(cls) -> list[Load]:
        return [
            joinedload(GameOutcome.time_update)
        ]

    def to_public(self) -> GameOutcomePublic:
        return GameOutcomePublic(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self, elo_updates: GameEndedEloUpdates | None) -> GameEndedBroadcastedData:
        return GameEndedBroadcastedData(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            time_update=GameTimeUpdatePublic.cast(self.time_update),
            elo=elo_updates
        )


class GameOutcomePublic(GameOutcomeBase):
    time_update: GameTimeUpdatePublic | None


class GameEndedBroadcastedData(GameOutcomeBase):
    time_update: GameTimeUpdatePublic | None
    elo: GameEndedEloUpdates | None
