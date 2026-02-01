from uuid import UUID
from sqlmodel import Field

from net.models import WebsocketWrapperDump
from other.datatypes import CompatibilityResolution
from pubsub.models.channel import EventChannel
from utils.custom_model import CustomModel, CustomSQLModel


class SavedQuery(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)


class CompatibilityCheckPayload(CustomModel):
    client_build: int
    min_server_build: int


class CompatibilityResponse(CustomModel):
    resolution: CompatibilityResolution
    server_build: int
    min_client_build: int


class MutableStateRequestPayload(CustomModel):
    unwrap_tokens: bool = False
    unwrap_subs: bool = False
    unwrap_timeout_timers: bool = False
    unwrap_challenge_cancelling_timers: bool = False


class MutableStatePublic(CustomModel):
    shutdown_activated: bool
    last_guest_id: int

    stored_tokens: int
    token_to_user: dict[str, str] = Field(default_factory=dict)

    stored_subs: int
    ws_subscribers: dict[EventChannel, dict[UUID, WebsocketWrapperDump]] = Field(default_factory=dict)

    stored_timeout_timers: int
    game_timeout_check_timers: dict[int, float] = Field(default_factory=dict)

    stored_challenge_cancelling_timers: int
    user_challenge_cancelling_timers: dict[str, float] = Field(default_factory=dict)
