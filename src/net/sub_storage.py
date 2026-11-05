from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, Iterable
from uuid import UUID
from pydantic import BaseModel

from common.models import UserActivity
from common.user_ref import UserReference
from net.models import WebsocketWrapperDump
from net.ws_wrapper import WebSocketWrapper
from pubsub.models.channel import EventChannel, EveryoneEventChannel
from pubsub.outgoing_event.base import OutgoingEvent
from utils.bijective_map import BijectiveMap



class SubscriberTag(StrEnum):
    WHITE_PLAYER = auto()
    BLACK_PLAYER = auto()


@dataclass
class HeldEvent:
    event: OutgoingEvent[Any, Any]
    tag_whitelist: set[SubscriberTag] | None
    tag_blacklist: set[SubscriberTag] | None


@dataclass
class Subscriber:
    ws: WebSocketWrapper
    tags: set[SubscriberTag]
    held: list[HeldEvent] | None = None  # set while the subscriber's refresh is being computed: events wait for it, so they never reach the client ahead of it

    def passes(self, tag_whitelist: set[SubscriberTag] | None, tag_blacklist: set[SubscriberTag] | None) -> bool:
        if tag_whitelist and tag_whitelist.difference(self.tags):
            return False
        if tag_blacklist and self.tags.intersection(tag_blacklist):
            return False
        return True


class SubscriberStorage:
    def __init__(self) -> None:
        self.subscribers: dict[EventChannel, dict[UUID, Subscriber]] = {}
        self._channels_by_ws: dict[UUID, set[EventChannel]] = {}

    @staticmethod
    def _resolve_websocket_reference(websocket_ref: WebSocketWrapper | UUID) -> UUID:
        return websocket_ref.uuid if isinstance(websocket_ref, WebSocketWrapper) else websocket_ref

    def __len__(self) -> int:
        uuids = {
            ws_uuid
            for subs in self.subscribers.values()
            for ws_uuid in subs.keys()
        }
        return len(uuids)

    def dump(self) -> dict[EventChannel, dict[UUID, WebsocketWrapperDump]]:
        return {
            channel: {
                ws_uuid: sub.ws.dump(list(map(str, sub.tags)))
                for ws_uuid, sub in subs.items()
            }
            for channel, subs in self.subscribers.items()
        }

    def subscribe(self, websocket: WebSocketWrapper, channel: EventChannel, tags: set[SubscriberTag] | None = None) -> None:
        self.subscribers.setdefault(channel, {})[websocket.uuid] = Subscriber(websocket, tags or set())
        self._channels_by_ws.setdefault(websocket.uuid, set()).add(channel)

    def hold_events(self, websocket: WebSocketWrapper, channel: EventChannel) -> None:
        """Until `send_refresh` or `release_events`, the events for the subscriber are kept back"""
        subscriber = self.subscribers.get(channel, {}).get(websocket.uuid)
        if subscriber is not None and subscriber.held is None:
            subscriber.held = []

    def send_refresh(self, websocket: WebSocketWrapper, channel: EventChannel, refresh: OutgoingEvent[Any, Any], tags: set[SubscriberTag] | None) -> None:
        """`tags` is None to keep the subscriber's. Sends the refresh, then the events that came while it was being computed (those may repeat what it already has)"""
        subscriber = self.subscribers.get(channel, {}).get(websocket.uuid)
        if subscriber is None:
            return  # unsubscribed meanwhile

        if tags is not None:
            subscriber.tags = tags
        websocket.send_event(refresh)
        self.release_events(websocket, channel)

    def release_events(self, websocket: WebSocketWrapper, channel: EventChannel) -> None:
        """Sends the held events, as the refresh isn't coming"""
        subscriber = self.subscribers.get(channel, {}).get(websocket.uuid)
        if subscriber is None or subscriber.held is None:
            return

        held, subscriber.held = subscriber.held, None
        for held_event in held:
            if subscriber.passes(held_event.tag_whitelist, held_event.tag_blacklist):
                websocket.send_event(held_event.event)

    def unsubscribe(self, websocket_ref: WebSocketWrapper | UUID, channel: EventChannel) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        self._remove(uuid, channel)
        ws_channels = self._channels_by_ws.get(uuid)
        if ws_channels is not None:
            ws_channels.discard(channel)
            if not ws_channels:
                del self._channels_by_ws[uuid]

    def fully_remove(self, websocket_ref: WebSocketWrapper | UUID) -> None:
        uuid = self._resolve_websocket_reference(websocket_ref)
        for channel in self._channels_by_ws.pop(uuid, set()):
            self._remove(uuid, channel)

    def _remove(self, uuid: UUID, channel: EventChannel) -> None:
        channel_subs = self.subscribers.get(channel)
        if channel_subs is None:
            return
        channel_subs.pop(uuid, None)
        if not channel_subs:
            del self.subscribers[channel]

    def get_subscriptions(self, websocket_ref: WebSocketWrapper | UUID) -> set[EventChannel]:
        uuid = self._resolve_websocket_reference(websocket_ref)
        return set(self._channels_by_ws.get(uuid, ()))

    def get_subscribed_channels[C: EventChannel](self, channel_type: type[C]) -> list[C]:
        return [
            channel
            for channel, subs in self.subscribers.items()
            if isinstance(channel, channel_type) and subs
        ]

    def count_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> int:
        return len(self.subscribers.get(channel, ()))

    def get_subscribers(self, channel: EventChannel = EveryoneEventChannel()) -> Iterable[Subscriber]:
        return list(self.subscribers.get(channel, {}).values())

    def has_ws_subscriber(self, websocket_ref: WebSocketWrapper | UUID, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self._resolve_websocket_reference(websocket_ref) in self.subscribers.get(channel, ())

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

    def get_user_activity_in_channel(
        self,
        token_map: BijectiveMap[str, UserReference],
        user_ref: UserReference,
        channel: EventChannel
    ) -> UserActivity | None:
        token = token_map.get_inverse(user_ref)
        if not token:
            return None

        most_recent_activity = None

        for subscriber in self.get_subscribers(channel):
            if subscriber.ws.saved_token != token:
                continue

            activity = subscriber.ws.get_activity_data()
            if not most_recent_activity or activity.last_active_unixsecs > most_recent_activity.last_active_unixsecs:
                most_recent_activity = activity

        return most_recent_activity

    async def broadcast[T: BaseModel | None, C: EventChannel](
        self,
        event_instance: OutgoingEvent[T, C],
        tag_whitelist: set[SubscriberTag] | None = None,
        tag_blacklist: set[SubscriberTag] | None = None
    ) -> None:
        for subscriber in self.get_subscribers(event_instance.target_channel):
            if subscriber.held is not None:
                subscriber.held.append(HeldEvent(event_instance, tag_whitelist, tag_blacklist))
            elif subscriber.passes(tag_whitelist, tag_blacklist):
                subscriber.ws.send_event(event_instance)
