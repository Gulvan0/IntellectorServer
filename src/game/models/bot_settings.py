from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship

from utils.custom_model import CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameBotSettings(CustomSQLModel, table=True):
    """Settings of the bot playing an external game, shared by every device of its uploader"""
    game_id: int | None = Field(default=None, primary_key=True, foreign_key="game.id")
    think_cap_secs: int | None = None  # none: the bot thinks as long as it likes

    game: Game = Relationship(back_populates="bot_settings")
