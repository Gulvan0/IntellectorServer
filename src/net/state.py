from asyncio import Event, Lock, TimerHandle
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from common.models import UserActivity
from common.user_ref import UserReference
from net.sub_storage import SubscriberStorage
from net.task_storage import ConcurrentTaskStorage
from player.models import PlayerStatusState
from pubsub.models.channel import EventChannel, EveryoneEventChannel
from utils.bijective_map import BijectiveMap


@dataclass
class GameActionLock:
    lock: Lock = field(default_factory=Lock)
    users: int = 0


@dataclass
class MutableState:
    shutdown_activated: bool = False
    exit_event: Event = field(default_factory=Event)  # set once the drained server may exit
    token_to_user: BijectiveMap[str, UserReference] = field(default_factory=BijectiveMap)
    ws_subscribers: SubscriberStorage = field(default_factory=SubscriberStorage)
    last_guest_id: int = 0
    game_timeout_check_timers: dict[int, TimerHandle] = field(default_factory=dict)
    game_presence_check_timers: dict[int, TimerHandle] = field(default_factory=dict)
    user_challenge_cancelling_timers: dict[UserReference, TimerHandle] = field(default_factory=dict)
    concurrent_tasks: ConcurrentTaskStorage = field(default_factory=ConcurrentTaskStorage)
    published_player_statuses: dict[str, PlayerStatusState] = field(default_factory=dict)  # by login, for the players someone subscribed to the status of

    __game_action_locks: dict[int, GameActionLock] = field(default_factory=dict)
    __guest_tokens: OrderedDict[str, None] = field(default_factory=OrderedDict)  # oldest first

    @asynccontextmanager
    async def game_action(self, game_id: int) -> AsyncIterator[None]:
        """Runs one action on a game at a time. Everything the action reads must be read inside, in a transaction begun
        inside; it must never wait on a client in here, nor enter this again for the same game"""
        entry = self.__game_action_locks.setdefault(game_id, GameActionLock())
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if not entry.users:
                del self.__game_action_locks[game_id]

    def add_guest(self, token: str, max_tokens: int) -> int:
        self.last_guest_id += 1
        self.token_to_user.update(token, UserReference.guest(self.last_guest_id))
        self.__guest_tokens[token] = None
        if len(self.__guest_tokens) > max_tokens:
            self.__evict_oldest_offline_guest()
        return self.last_guest_id

    def __evict_oldest_offline_guest(self) -> None:
        """Guest tokens are the only ones that pile up, as a player has just one. An evicted guest becomes a new one, same as after a restart"""
        connected_tokens = {subscriber.ws.saved_token for subscriber in self.ws_subscribers.get_subscribers()}
        token = next((token for token in self.__guest_tokens if token not in connected_tokens), None)
        if token:
            del self.__guest_tokens[token]
            self.token_to_user.leftpop(token)

    def add_logged(self, token: str, login: str) -> None:
        user = UserReference.logged(login)
        self.token_to_user.update(token, user)

    def has_user_subscriber(self, user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self.ws_subscribers.has_user_subscriber(self.token_to_user, user_ref, channel)

    def has_guest_session(self, guest: UserReference) -> bool:
        return self.token_to_user.get_inverse(guest) is not None

    def get_user_activity_in_channel(self, user_ref: UserReference, channel: EventChannel) -> UserActivity | None:
        return self.ws_subscribers.get_user_activity_in_channel(self.token_to_user, user_ref, channel)
