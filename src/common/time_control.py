from __future__ import annotations

from enum import StrEnum, auto
from typing import Protocol, assert_never, runtime_checkable


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
