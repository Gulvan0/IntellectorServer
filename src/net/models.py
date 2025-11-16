from pydantic import BaseModel, Field


class WebsocketIncomingMessage(BaseModel):
    event: str
    token: str | None = None
    body: dict = Field(default_factory=dict)


class NewSubscriberBroadcastedData(BaseModel):
    user_ref: str | None


class SubscriberLeftBroadcastedData(BaseModel):
    user_ref: str | None


class SubscriberListChannelStateRefresh(BaseModel):
    current_subscriber_user_refs: list[str]
    unauthenticated_subs_count: int
