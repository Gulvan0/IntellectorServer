from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, DefaultDict, Iterable
from uuid import UUID

from pydantic import BaseModel
from models.channel import EventChannel, EveryoneEventChannel
from utils.datatypes import UserReference, UserStatus
from utils.ds import BijectiveMap

if TYPE_CHECKING:
    from net.fastapi_wrapper import WebSocketWrapper
    from net.outgoing import WebsocketOutgoingEvent


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

    def count_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> int:
        return len(self.subscribers[channel])

    def get_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> Iterable[WebSocketWrapper]:
        return self.subscribers[channel].values()

    def has_ws_subscriber(self, websocket_ref: WebSocketWrapper | UUID, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self._resolve_websocket_reference(websocket_ref) in self.subscribers[channel]

    def has_token_subscriber(self, token: str, channel: EventChannel = EveryoneEventChannel()) -> bool:
        for ws in self.get_subscribers(channel):
            if ws.saved_token and ws.saved_token == token:
                return True
        return False

    def has_user_subscriber(self, token_map: BijectiveMap[str, UserReference], user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        token = token_map.get_inverse(user_ref)
        return self.has_token_subscriber(token, channel) if token else False

    def get_user_status_in_channel(self, token_map: BijectiveMap[str, UserReference], user_ref: UserReference, channel: EventChannel) -> UserStatus:
        token = token_map.get_inverse(user_ref)
        if not token:
            return UserStatus.OFFLINE

        most_active_status_over_connections = UserStatus.OFFLINE

        for ws in self.get_subscribers(channel):
            if ws.saved_token != token:
                continue

            iterated_status = ws.get_status()
            if iterated_status.is_more_active_than(most_active_status_over_connections):
                most_active_status_over_connections = iterated_status

        return most_active_status_over_connections

    async def broadcast[T: BaseModel, C: EventChannel](self, event: WebsocketOutgoingEvent[T, C], payload: T, channel: C = EveryoneEventChannel()) -> None:  # type: ignore
        sending_coroutines = [websocket.send_event(event, payload, channel) for websocket in self.subscribers[channel].values()]
        await asyncio.gather(*sending_coroutines)
