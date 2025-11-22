from enum import StrEnum, auto
from sqlmodel import Field

from src.utils.custom_model import CustomSQLModel


class NotificationApp(StrEnum):
    # TELEGRAM = auto()  To be implemented later
    VK = auto()


class StoredNotificationBase(CustomSQLModel):
    id: int | None = Field(default=None, primary_key=True)
    app: NotificationApp
    chat_id: int
    message_id: int
    is_permanent: bool = False


class GameStartedNotification(StoredNotificationBase, is_table=True):
    game_id: int


class NewPublicChallengeNotification(StoredNotificationBase, is_table=True):
    challenge_id: int
