from enum import StrEnum, auto


class CompatibilityResolution(StrEnum):
    COMPATIBLE = auto()
    OUTDATED_CLIENT = auto()
    OUTDATED_SERVER = auto()
