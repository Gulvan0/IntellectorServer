from typing import TYPE_CHECKING, Literal
from sqlalchemy.orm import Load, joinedload
from sqlmodel import Field, Relationship

from board.piece import PieceColor
from common.field_types import CurrentDatetime, Sip
from game.datatypes import EventKind
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from utils.custom_model import CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameRollbackEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    event_index: int
    ply_cnt_before: int
    ply_cnt_after: int
    requested_by: PieceColor


class GameRollbackEvent(GameRollbackEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: Game = Relationship(back_populates="rollback_events")
    time_update: GameTimeUpdate | None = Relationship()

    @classmethod
    def load_options(cls) -> list[Load]:
        return [
            joinedload(GameRollbackEvent.time_update)
        ]

    def to_public(self) -> GameRollbackEventPublic:
        return GameRollbackEventPublic(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self, updated_sip: str) -> RollbackBroadcastedData:
        return RollbackBroadcastedData(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=GameTimeUpdatePublic.cast(self.time_update),
            updated_sip=updated_sip
        )


class GameRollbackEventPublic(GameRollbackEventBase):
    event_kind: Literal[EventKind.ROLLBACK] = EventKind.ROLLBACK
    time_update: GameTimeUpdatePublic | None


class RollbackBroadcastedData(GameRollbackEventBase):
    time_update: GameTimeUpdatePublic | None
    updated_sip: Sip
