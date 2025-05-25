from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, DefaultDict, Iterable
from uuid import UUID

from pydantic import BaseModel
from models.channel import EVERYONE, EventChannel, EveryoneEventChannel
from models.config import MainConfig, SecretConfig
from utils.config_loader import retrieve_config
from utils.ds import BijectiveMap

if TYPE_CHECKING:
    from utils.fastapi_wrappers import WebSocketWrapper, WebsocketOutgoingEvent


@dataclass(frozen=True)
class UserReference:
    reference: str

    @classmethod
    def logged(cls, login: str) -> UserReference:
        return UserReference(login)

    @classmethod
    def guest(cls, id: int) -> UserReference:
        return UserReference(f"_{id}")

    def is_guest(self) -> bool:
        return self.reference.startswith("_")

    @property
    def login(self) -> str:
        assert not self.is_guest()
        return self.reference

    @property
    def guest_id(self) -> int:
        assert self.is_guest()
        return int(self.reference[1:])

    def __str__(self) -> str:
        return self.reference


class SubscriberStorage:
    subscribers: DefaultDict[EventChannel, dict[UUID, WebSocketWrapper]] = defaultdict(dict)

    @staticmethod
    def _resolve_websocket_reference(websocket_ref: WebSocketWrapper | UUID) -> UUID:
        return websocket_ref.uuid if isinstance(websocket_ref, WebSocketWrapper) else websocket_ref

    def subscribe(self, websocket: WebSocketWrapper, channel: EventChannel) -> None:
        self.subscribers[channel][websocket.uuid] = websocket

    def unsubscribe(self, websocket_ref: WebSocketWrapper | UUID, channel: EventChannel) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        self.subscribers[channel].pop(uuid, None)

    def fully_remove(self, websocket_ref: WebSocketWrapper | UUID) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        for channel_subs in self.subscribers.values():
            channel_subs.pop(uuid, None)

    def get_subscriptions(self, websocket_ref: WebSocketWrapper | UUID) -> set[EventChannel]:
        uuid = self._resolve_websocket_reference(websocket_ref)
        return set(channel for channel, channel_subs in self.subscribers.items() if uuid in channel_subs)

    def count_subscribers(self, channel: EventChannel = EVERYONE) -> int:
        return len(self.subscribers[channel])

    def get_subscribers(self, channel: EventChannel = EVERYONE) -> Iterable[WebSocketWrapper]:
        return self.subscribers[channel].values()

    def broadcast[T: BaseModel](self, event: WebsocketOutgoingEvent[T], payload: T, channel: EventChannel = EVERYONE) -> None:
        for websocket in self.subscribers[channel].values():
            websocket.send_event(event, payload)


class GlobalState:
    shutdown_activated: bool = False  # TODO: Admin shutdown endpoint
    token_to_user: BijectiveMap[str, UserReference] = BijectiveMap()
    last_guest_id: int = 0
    ws_subscribers: SubscriberStorage = SubscriberStorage()
    main_config: MainConfig = retrieve_config('main', MainConfig)
    secret_config: SecretConfig = retrieve_config('secret', SecretConfig)

    @classmethod
    def add_guest(cls, token: str) -> int:
        cls.last_guest_id += 1
        cls.token_to_user.add(token, UserReference.guest(cls.last_guest_id))
        return cls.last_guest_id

    @classmethod
    def add_logged(cls, token: str, login: str) -> None:
        cls.token_to_user.add(token, UserReference.logged(login))
