from enum import auto, Enum


class ChallengeKind(Enum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    DIRECT = auto()


class TimeControlKind(Enum):
    HYPERBULLET = auto()
    BULLET = auto()
    BLITZ = auto()
    RAPID = auto()
    CLASSIC = auto()
    CORRESPONDENCE = auto()


class ChallengeAcceptorColor(Enum):
    WHITE = auto()
    BLACK = auto()
    RANDOM = auto()


class OutcomeKind(Enum):
    MATE = auto()
    BREAKTHROUGH = auto()
    TIMEOUT = auto()
    RESIGN = auto()
    ABANDON = auto()
    DRAW_AGREEMENT = auto()
    REPETITION = auto()
    NO_PROGRESS = auto()
    ABORT = auto()


class OfferKind(Enum):
    DRAW = auto()
    TAKEBACK = auto()


class OfferAction(Enum):
    CREATE = auto()
    CANCEL = auto()
    ACCEPT = auto()
    DECLINE = auto()


class UserRole(Enum):
    ADMIN = auto()
    ANACONDA_DEVELOPER = auto()


class UserRestrictionKind(Enum):
    RATED_GAMES = auto()
    SET_AVATAR = auto()
    CHAT = auto()


class StudyPublicity(Enum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    PRIVATE = auto()
