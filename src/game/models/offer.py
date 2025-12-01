from sqlmodel import Field, Relationship

from src.rules import PieceColor
from src.common.field_types import CurrentDatetime
from src.game.datatypes import OfferAction, OfferKind
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GameOfferEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColor


class GameOfferEvent(GameOfferEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: game_main_models.Game = Relationship(back_populates="offer_events")

    def to_broadcasted_data(self) -> "OfferActionBroadcastedData":
        return OfferActionBroadcastedData.cast(self)


class GameOfferEventPublic(GameOfferEventBase):
    pass


class OfferActionBroadcastedData(GameOfferEventBase):
    game_id: int
