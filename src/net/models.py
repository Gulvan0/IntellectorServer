from pydantic import Field

from src.utils.custom_model import CustomModel


class WebsocketIncomingMessage(CustomModel):
    event: str
    token: str | None = None
    body: dict = Field(default_factory=dict)


class NewSubscriberBroadcastedData(CustomModel):
    user_ref: str | None


class SubscriberLeftBroadcastedData(CustomModel):
    user_ref: str | None
