from enum import StrEnum, auto
from sqlmodel import Field

from common.field_types import CurrentDatetime
from utils.custom_model import CustomSQLModel


class NotificationApp(StrEnum):
    # TELEGRAM = auto()  To be implemented later
    VK = auto()


class StoredNotificationBase(CustomSQLModel):
    id: int | None = Field(default=None, primary_key=True)
    sent_at: CurrentDatetime
    app: NotificationApp
    chat_id: int
    message_id: int
    is_permanent: bool = False


class GameStartedNotification(StoredNotificationBase, table=True):
    game_id: int


class NewPublicChallengeNotification(StoredNotificationBase, table=True):
    challenge_id: int
