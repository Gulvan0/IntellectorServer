from asyncio import Lock, TimerHandle
from dataclasses import dataclass, field

from common.models import UserActivity
from common.user_ref import UserReference
from net.sub_storage import SubscriberStorage
from net.task_storage import ConcurrentTaskStorage
from pubsub.models.channel import EventChannel, EveryoneEventChannel
from utils.bijective_map import BijectiveMap


@dataclass
class MutableState:
    shutdown_activated: bool = False
    token_to_user: BijectiveMap[str, UserReference] = field(default_factory=BijectiveMap)
    ws_subscribers: SubscriberStorage = field(default_factory=SubscriberStorage)
    last_guest_id: int = 0
    game_timeout_check_timers: dict[int, TimerHandle] = field(default_factory=dict)
    user_challenge_cancelling_timers: dict[UserReference, TimerHandle] = field(default_factory=dict)
    concurrent_tasks: ConcurrentTaskStorage = field(default_factory=ConcurrentTaskStorage)

    __game_end_locks: dict[int, Lock] = field(default_factory=dict)

    def get_game_end_lock(self, game_id: int) -> Lock:
        return self.__game_end_locks.setdefault(game_id, Lock())

    def release_game_end_lock(self, game_id: int) -> None:
        self.__game_end_locks.pop(game_id, None)

    def add_guest(self, token: str) -> int:
        self.last_guest_id += 1
        self.token_to_user.update(token, UserReference.guest(self.last_guest_id))
        return self.last_guest_id

    def add_logged(self, token: str, login: str) -> None:
        user = UserReference.logged(login)
        self.token_to_user.update(token, user)

    def has_user_subscriber(self, user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self.ws_subscribers.has_user_subscriber(self.token_to_user, user_ref, channel)

    def get_user_activity_in_channel(self, user_ref: UserReference, channel: EventChannel) -> UserActivity | None:
        return self.ws_subscribers.get_user_activity_in_channel(self.token_to_user, user_ref, channel)
