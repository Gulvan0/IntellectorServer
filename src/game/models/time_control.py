from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship

from common.time_control import FischerTimeControlEntity
from utils.custom_model import CustomSQLModel


class GameFischerTimeControlBase(CustomSQLModel):
    start_seconds: int
    increment_seconds: int = 0


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = GameFischerTimeControlBase
    from game.models.main import Game


class GameFischerTimeControl(GameFischerTimeControlBase, table=True):
    game_id: int | None = Field(default=None, primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="fischer_time_control")


class GameFischerTimeControlPublic(GameFischerTimeControlBase):
    pass


class GameFischerTimeControlCreate(GameFischerTimeControlBase):
    pass
