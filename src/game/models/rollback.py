from sqlmodel import Field, Relationship

from src.rules import PieceColor
from src.common.field_types import CurrentDatetime, Sip
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GameRollbackEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    ply_cnt_before: int
    ply_cnt_after: int
    requested_by: PieceColor


class GameRollbackEvent(GameRollbackEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: game_main_models.Game = Relationship(back_populates="rollback_events")
    time_update: GameTimeUpdate | None = Relationship()

    def to_public(self) -> "GameRollbackEventPublic":
        return GameRollbackEventPublic(
            occurred_at=self.occurred_at,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self, updated_sip: str) -> "RollbackBroadcastedData":
        return RollbackBroadcastedData(
            occurred_at=self.occurred_at,
            ply_cnt_before=self.ply_cnt_before,
            ply_cnt_after=self.ply_cnt_after,
            requested_by=self.requested_by,
            time_update=GameTimeUpdatePublic.cast(self.time_update),
            game_id=self.game_id,
            updated_sip=updated_sip
        )


class GameRollbackEventPublic(GameRollbackEventBase):
    time_update: GameTimeUpdatePublic | None


class RollbackBroadcastedData(GameRollbackEventBase):
    game_id: int
    time_update: GameTimeUpdatePublic | None
    updated_sip: Sip
