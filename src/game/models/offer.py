from typing import TYPE_CHECKING, Literal
from sqlmodel import Field, Relationship

from board.piece import PieceColor
from common.field_types import CurrentDatetime
from game.datatypes import EventKind, OfferAction, OfferKind
from utils.custom_model import CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameOfferEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColor


class GameOfferEvent(GameOfferEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="offer_events")

    def to_broadcasted_data(self) -> OfferActionBroadcastedData:
        return OfferActionBroadcastedData.cast(self)


class GameOfferEventPublic(GameOfferEventBase):
    event_kind: Literal[EventKind.OFFER] = EventKind.OFFER


class OfferActionBroadcastedData(GameOfferEventBase):
    pass
