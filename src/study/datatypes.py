from enum import auto, StrEnum


class StudyPublicity(StrEnum):
    PUBLIC = auto()
    PROFILE_AND_LINK_ONLY = auto()
    LINK_ONLY = auto()
    PRIVATE = auto()
