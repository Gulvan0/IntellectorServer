from __future__ import annotations

from dataclasses import dataclass
from enum import auto, StrEnum
from typing import Protocol, assert_never, runtime_checkable


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


class ChallengeKind(StrEnum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    DIRECT = auto()


@runtime_checkable
class FischerTimeControlEntity(Protocol):
    start_seconds: int
    increment_seconds: int


class TimeControlKind(StrEnum):
    HYPERBULLET = auto()
    BULLET = auto()
    BLITZ = auto()
    RAPID = auto()
    CLASSIC = auto()
    CORRESPONDENCE = auto()

    @classmethod
    def of(cls, entity: FischerTimeControlEntity | None) -> TimeControlKind:
        match entity:
            case FischerTimeControlEntity():  # Adding another time control type => adding new Protocol and a separate case for it
                determinant = entity.start_seconds + 40 * entity.increment_seconds
                if determinant < 60:
                    return TimeControlKind.HYPERBULLET
                elif determinant < 3 * 60:
                    return TimeControlKind.BULLET
                elif determinant < 10 * 60:
                    return TimeControlKind.BLITZ
                elif determinant < 60 * 60:
                    return TimeControlKind.RAPID
                else:
                    return TimeControlKind.CLASSIC
            case None:
                return TimeControlKind.CORRESPONDENCE
            case _:
                assert_never(entity)


class ChallengeAcceptorColor(StrEnum):
    WHITE = auto()
    BLACK = auto()
    RANDOM = auto()

    def mergeable_with(self, other: ChallengeAcceptorColor) -> bool:
        return self == ChallengeAcceptorColor.RANDOM or other == ChallengeAcceptorColor.RANDOM or self != other


class OutcomeKind(StrEnum):
    MATE = auto()
    BREAKTHROUGH = auto()
    TIMEOUT = auto()
    RESIGN = auto()
    ABANDON = auto()
    DRAW_AGREEMENT = auto()
    REPETITION = auto()
    NO_PROGRESS = auto()
    ABORT = auto()


class OfferKind(StrEnum):
    DRAW = auto()
    TAKEBACK = auto()


class OfferAction(StrEnum):
    CREATE = auto()
    CANCEL = auto()
    ACCEPT = auto()
    DECLINE = auto()


class UserRole(StrEnum):
    ADMIN = auto()
    ANACONDA_DEVELOPER = auto()


class UserRestrictionKind(StrEnum):
    RATED_GAMES = auto()
    SET_AVATAR = auto()
    CHAT = auto()


class StudyPublicity(StrEnum):
    PUBLIC = auto()
    PROFILE_AND_LINK_ONLY = auto()
    LINK_ONLY = auto()
    PRIVATE = auto()


class UserStatus(StrEnum):
    ONLINE = auto()
    AWAY = auto()
    OFFLINE = auto()

    def is_more_active_than(self, other: UserStatus) -> bool:
        match other:
            case UserStatus.AWAY:
                return self == UserStatus.ONLINE
            case UserStatus.OFFLINE:
                return self != UserStatus.OFFLINE
            case _:
                return False
