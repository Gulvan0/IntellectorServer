from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import DefaultDict, Iterable
from uuid import UUID
from pydantic import BaseModel

from src.common.user_ref import UserReference
from src.pubsub.models.channel import EventChannel, EveryoneEventChannel
from src.player.datatypes import UserStatus
from src.utils.bijective_map import BijectiveMap

import asyncio
import src.net.core as core
import src.net.outgoing as outgoing


class SubscriberTag(Enum):
    PARTICIPATING_PLAYER = auto()


@dataclass
class Subscriber:
    ws: core.WebSocketWrapper
    tags: set[SubscriberTag]


class SubscriberStorage:
    subscribers: DefaultDict[EventChannel, dict[UUID, Subscriber]] = defaultdict(dict)

    @staticmethod
    def _resolve_websocket_reference(websocket_ref: core.WebSocketWrapper | UUID) -> UUID:
        return websocket_ref.uuid if isinstance(websocket_ref, core.WebSocketWrapper) else websocket_ref

    def subscribe(self, websocket: core.WebSocketWrapper, channel: EventChannel, tags: set[SubscriberTag] | None = None) -> None:
        self.subscribers[channel][websocket.uuid] = Subscriber(websocket, tags or set())

    def unsubscribe(self, websocket_ref: core.WebSocketWrapper | UUID, channel: EventChannel) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        self.subscribers[channel].pop(uuid, None)

    def fully_remove(self, websocket_ref: core.WebSocketWrapper | UUID) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        for channel_subs in self.subscribers.values():
            channel_subs.pop(uuid, None)

    def get_subscriptions(self, websocket_ref: core.WebSocketWrapper | UUID) -> set[EventChannel]:
        uuid = self._resolve_websocket_reference(websocket_ref)
        return set(channel for channel, channel_subs in self.subscribers.items() if uuid in channel_subs)

    def count_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> int:
        return len(self.subscribers[channel])

    def get_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> Iterable[Subscriber]:
        return self.subscribers[channel].values()

    def has_ws_subscriber(self, websocket_ref: core.WebSocketWrapper | UUID, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self._resolve_websocket_reference(websocket_ref) in self.subscribers[channel]

    def has_token_subscriber(self, token: str, channel: EventChannel = EveryoneEventChannel()) -> bool:
        for subscriber in self.get_subscribers(channel):
            if subscriber.ws.saved_token and subscriber.ws.saved_token == token:
                return True
        return False

    def has_user_subscriber(
        self,
        token_map: BijectiveMap[str, UserReference],
        user_ref: UserReference,
        channel: EventChannel = EveryoneEventChannel()
    ) -> bool:
        token = token_map.get_inverse(user_ref)
        return self.has_token_subscriber(token, channel) if token else False

    def get_user_status_in_channel(
        self,
        token_map: BijectiveMap[str, UserReference],
        user_ref: UserReference,
        channel: EventChannel
    ) -> UserStatus:
        token = token_map.get_inverse(user_ref)
        if not token:
            return UserStatus.OFFLINE

        most_active_status_over_connections = UserStatus.OFFLINE

        for subscriber in self.get_subscribers(channel):
            if subscriber.ws.saved_token != token:
                continue

            iterated_status = subscriber.ws.get_status()
            if iterated_status.is_more_active_than(most_active_status_over_connections):
                most_active_status_over_connections = iterated_status

        return most_active_status_over_connections

    async def broadcast[T: BaseModel, C: EventChannel](
        self,
        event: outgoing.WebsocketOutgoingEvent[T, C],
        payload: T,
        channel: C,
        tag_whitelist: set[SubscriberTag] | None = None,
        tag_blacklist: set[SubscriberTag] | None = None
    ) -> None:
        sending_coroutines = []
        for subscriber in self.get_subscribers(channel):
            if tag_whitelist and tag_whitelist.difference(subscriber.tags):
                continue
            if tag_blacklist and subscriber.tags.intersection(tag_blacklist):
                continue
            sending_coroutines.append(subscriber.ws.send_event(event, payload, channel))
        await asyncio.gather(*sending_coroutines)
