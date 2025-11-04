from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from rules import PieceColor

from ..column_types import CurrentDatetime
from utils.datatypes import OfferAction, OfferKind


if TYPE_CHECKING:
    from .main import Game


class GameOfferEventBase(SQLModel):
    occurred_at: CurrentDatetime
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColor


class GameOfferEvent(GameOfferEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="offer_events")


class GameOfferEventPublic(GameOfferEventBase):
    pass


class OfferActionBroadcastedData(GameOfferEventBase):
    game_id: int
