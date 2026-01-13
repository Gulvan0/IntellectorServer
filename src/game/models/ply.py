from sqlmodel import Field, Relationship

from src.rules.piece import PieceColor, PieceKind
from src.common.field_types import CurrentDatetime, Sip
from src.game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
from src.rules.ply import PlyKind
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GamePlyEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    ply_index: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None


class GamePlyEvent(GamePlyEventBase, table=True):  # Analytics-optimized
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    is_cancelled: bool = False
    kind: PlyKind
    moving_color: PieceColor
    moved_piece: PieceKind
    target_piece: PieceKind | None = None
    sip_after: Sip
    time_update_id: int | None = Field(default=None, foreign_key="gametimeupdate.id")

    game: game_main_models.Game = Relationship(back_populates="ply_events")
    time_update: GameTimeUpdate | None = Relationship()

    def to_public(self) -> "GamePlyEventPublic":
        return GamePlyEventPublic(
            occurred_at=self.occurred_at,
            ply_index=self.ply_index,
            from_i=self.from_i,
            from_j=self.from_j,
            to_i=self.to_i,
            to_j=self.to_j,
            morph_into=self.morph_into,
            is_cancelled=self.is_cancelled,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )

    def to_broadcasted_data(self) -> "PlyBroadcastedData":
        return PlyBroadcastedData(
            occurred_at=self.occurred_at,
            ply_index=self.ply_index,
            from_i=self.from_i,
            from_j=self.from_j,
            to_i=self.to_i,
            to_j=self.to_j,
            morph_into=self.morph_into,
            game_id=self.game_id,
            sip_after=self.sip_after,
            time_update=GameTimeUpdatePublic.cast(self.time_update)
        )


class GamePlyEventPublic(GamePlyEventBase):
    time_update: GameTimeUpdatePublic | None
    is_cancelled: bool = False


class PlyBroadcastedData(GamePlyEventBase):
    game_id: int
    sip_after: Sip
    time_update: GameTimeUpdatePublic | None
