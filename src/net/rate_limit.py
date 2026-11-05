from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
import time

from starlette.datastructures import Address

from config.models import RateLimitParams, RateLimitRule


UNKNOWN_HOST = "unknown"
SWEEP_INTERVAL_SECS = 60


class RateLimitGroup(StrEnum):
    """Each group has its own budget, named the same in `RateLimitParams`"""
    HTTP_BY_IP = auto()
    GENERAL = auto()
    SIGNIN = auto()
    SIGNIN_FAILURES = auto()
    REGISTRATION = auto()
    GUEST = auto()
    GAME_CREATION = auto()
    GAME_ACTION = auto()
    CHAT = auto()
    WRITE = auto()
    SEARCH = auto()
    WS_CONNECT = auto()
    WS_MESSAGE = auto()
    CLIENT_ERROR = auto()


def client_host(client: Address | None) -> str:
    return client.host if client else UNKNOWN_HOST


@dataclass
class _Bucket:
    tokens: float
    updated_at: float
    refilled_at: float  # no need to remember the bucket from this moment on: a new one would be just as full


class RateLimiter:
    """Token buckets, kept in memory: the server is a single process, and the limits may start over when it restarts"""

    def __init__(self, params: RateLimitParams, clock: Callable[[], float] = time.monotonic) -> None:
        self.__rules: dict[RateLimitGroup, RateLimitRule] = {group: getattr(params, group.value) for group in RateLimitGroup}
        self.__max_connections_per_ip = params.max_ws_connections_per_ip
        self.__clock = clock
        self.__buckets: dict[tuple[RateLimitGroup, str], _Bucket] = {}
        self.__next_sweep_at = clock() + SWEEP_INTERVAL_SECS
        self.__connections_by_ip: dict[str, int] = {}

    def __sweep_if_due(self, now: float) -> None:
        if now < self.__next_sweep_at:
            return
        self.__next_sweep_at = now + SWEEP_INTERVAL_SECS
        self.__buckets = {key: bucket for key, bucket in self.__buckets.items() if bucket.refilled_at > now}

    def __refilled_tokens(self, group: RateLimitGroup, key: str, now: float) -> float:
        rule = self.__rules[group]
        bucket = self.__buckets.get((group, key))
        if not bucket:
            return rule.max_requests
        return min(rule.max_requests, bucket.tokens + (now - bucket.updated_at) * rule.max_requests / rule.window_secs)

    def __secs_until_token(self, group: RateLimitGroup, tokens: float) -> float:
        rule = self.__rules[group]
        return (1 - tokens) * rule.window_secs / rule.max_requests

    def __store(self, group: RateLimitGroup, key: str, tokens: float, now: float) -> None:
        rule = self.__rules[group]
        self.__buckets[(group, key)] = _Bucket(tokens, now, now + (rule.max_requests - tokens) * rule.window_secs / rule.max_requests)

    def take(self, group: RateLimitGroup, key: str) -> float | None:
        """Spends one request of `key`'s budget. If it's used up, spends nothing and returns the seconds until a request is available"""
        now = self.__clock()
        self.__sweep_if_due(now)

        tokens = self.__refilled_tokens(group, key, now)
        if tokens < 1:
            return self.__secs_until_token(group, tokens)

        self.__store(group, key, tokens - 1, now)
        return None

    def give_back(self, group: RateLimitGroup, key: str) -> None:
        """Returns a spent request, for budgets only some outcomes of a request spend. Spending up front and giving back
        means requests in progress at the same time can't all slip past a budget that has room for just one of them"""
        now = self.__clock()
        tokens = self.__refilled_tokens(group, key, now)
        self.__store(group, key, min(self.__rules[group].max_requests, tokens + 1), now)

    def open_connection(self, host: str) -> bool:
        """Whether `host` may have one more connection. If true, it has to be released with `close_connection` eventually"""
        connections = self.__connections_by_ip.get(host, 0)
        if connections >= self.__max_connections_per_ip:
            return False
        self.__connections_by_ip[host] = connections + 1
        return True

    def close_connection(self, host: str) -> None:
        connections = self.__connections_by_ip[host] - 1
        if connections:
            self.__connections_by_ip[host] = connections
        else:
            del self.__connections_by_ip[host]
