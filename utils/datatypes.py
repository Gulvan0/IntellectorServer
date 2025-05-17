from __future__ import annotations

from enum import auto, StrEnum


class EventChannel:
    DEFAULT = 'default'
    OPEN_CHALLENGES = 'open_challenges'
    ACTIVE_GAMES = 'active_games'

    @staticmethod
    def direct_challenges(login: str) -> str:
        return f'challenge/direct/{login}'

    @staticmethod
    def game_public(game_id: int) -> str:
        return f'game/{game_id}/public'

    @staticmethod
    def game_spectator_only(game_id: int) -> str:
        return f'game/{game_id}/spectator_only'

    @staticmethod
    def started_player_games(watched_login: str) -> str:
        return f'player/{watched_login}/started_games'


class ChallengeKind(StrEnum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    DIRECT = auto()


class TimeControlKind(StrEnum):
    HYPERBULLET = auto()
    BULLET = auto()
    BLITZ = auto()
    RAPID = auto()
    CLASSIC = auto()
    CORRESPONDENCE = auto()


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
