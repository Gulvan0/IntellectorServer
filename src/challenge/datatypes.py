from __future__ import annotations

from enum import auto, StrEnum


class ChallengeKind(StrEnum):
    PUBLIC = auto()
    LINK_ONLY = auto()
    DIRECT = auto()


class ChallengeAcceptorColor(StrEnum):
    WHITE = auto()
    BLACK = auto()
    RANDOM = auto()

    def mergeable_with(self, other: ChallengeAcceptorColor) -> bool:
        return self == ChallengeAcceptorColor.RANDOM or other == ChallengeAcceptorColor.RANDOM or self != other
