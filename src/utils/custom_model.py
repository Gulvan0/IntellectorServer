from __future__ import annotations
from typing import Self, overload

from pydantic import BaseModel
from sqlmodel import SQLModel


def cast[T: BaseModel](source: BaseModel | None, target: type[T]) -> T | None:
    return target.model_construct(**source.model_dump()) if source else None


class CustomModel(BaseModel):
    @overload
    @classmethod
    def cast(cls, source: BaseModel) -> Self:
        ...

    @overload
    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        ...

    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        return cast(source, cls)


class CustomFrozenModel(BaseModel, frozen=True):
    @overload
    @classmethod
    def cast(cls, source: BaseModel) -> Self:
        ...

    @overload
    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        ...

    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        return cast(source, cls)


class CustomSQLModel(SQLModel):
    @overload
    @classmethod
    def cast(cls, source: BaseModel) -> Self:
        ...

    @overload
    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        ...

    @classmethod
    def cast(cls, source: BaseModel | None) -> Self | None:
        return cast(source, cls)
