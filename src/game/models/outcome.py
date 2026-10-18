from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy.orm import Load, joinedload
from sqlmodel import Field, Relationship

from board.piece import PieceColor
from common.field_types import legacy_nullable_datetime_field
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from game.datatypes import OutcomeKind
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameOutcomeBase(CustomSQLModel):
    game_ended_at: datetime | None = legacy_nullable_datetime_field()
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
    # rating changes of a rated game; null otherwise
    white_elo_delta: int | None = None
    black_elo_delta: int | None = None

    game: Game = Relationship(back_populates="outcome")
    time_update: GameTimeUpdate | None = Relationship()

    @classmethod
    def load_options(cls) -> list:
        return [
            joinedload(GameOutcome.time_update)  # type: ignore[arg-type]
        ]

    def to_public(self) -> GameOutcomePublic:
        return GameOutcomePublic(
            game_ended_at=self.game_ended_at,
            kind=self.kind,
            winner=self.winner,
            time_update=GameTimeUpdatePublic.cast(self.time_update),
            white_elo_delta=self.white_elo_delta,
            black_elo_delta=self.black_elo_delta
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
    white_elo_delta: int | None = None
    black_elo_delta: int | None = None


class GameEndedBroadcastedData(GameOutcomeBase):
    time_update: GameTimeUpdatePublic | None
    elo: GameEndedEloUpdates | None
