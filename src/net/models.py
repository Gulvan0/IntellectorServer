from typing import Any
from pydantic import Field

from player.datatypes import UserStatus
from utils.custom_model import CustomModel


class WebsocketIncomingMessage(CustomModel):
    event: str
    token: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)


class NewSubscriberBroadcastedData(CustomModel):
    user_ref: str | None


class SubscriberLeftBroadcastedData(CustomModel):
    user_ref: str | None


class WebsocketWrapperDump(CustomModel):
    last_activity: int
    last_message: int
    status: UserStatus
    saved_token: str | None
    saved_user_ref: str | None
    tags: list[str]
