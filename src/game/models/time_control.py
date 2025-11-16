from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

from src.common.time_control import FischerTimeControlEntity
import src.game.models.main as game_main_models


class GameFischerTimeControlBase(SQLModel):
    start_seconds: int
    increment_seconds: int = 0


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = GameFischerTimeControlBase


class GameFischerTimeControl(GameFischerTimeControlBase, table=True):
    game_id: int | None = Field(default=None, primary_key=True, foreign_key="game.id")

    game: game_main_models.Game = Relationship(back_populates="fischer_time_control")


class GameFischerTimeControlPublic(GameFischerTimeControlBase):
    pass


class GameFischerTimeControlCreate(GameFischerTimeControlBase):
    pass
