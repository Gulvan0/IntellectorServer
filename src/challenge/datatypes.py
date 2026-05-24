from enum import auto, StrEnum


class ChallengeKind(StrEnum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    DIRECT = auto()


class ChallengeAcceptorColor(StrEnum):
    WHITE = auto()
    BLACK = auto()
    RANDOM = auto()
