from datetime import datetime
from sqlmodel import Field

from common.field_types import PreciseUtcDateTime
from game.models.time_update import GameTimeUpdatePublic
from utils.custom_model import CustomModel, CustomSQLModel


class GameUploaderPresence(CustomSQLModel, table=True):
    """When an external game's uploader was last heard from, and since when the game has been suspended because of its silence"""
    game_id: int | None = Field(default=None, primary_key=True, foreign_key="game.id")
    last_seen_at: datetime = Field(sa_type=PreciseUtcDateTime)
    suspended_at: datetime | None = Field(default=None, sa_type=PreciseUtcDateTime)


class GameSuspensionBroadcastedData(CustomModel):
    event_index: int
    suspended: bool
    last_seen_at: datetime
    time_update: GameTimeUpdatePublic | None  # the bot's clock frozen or restarted by the change; none if no clock was affected

