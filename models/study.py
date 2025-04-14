from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from .utils import CURRENT_DATETIME_COLUMN, SIP_COLUMN
from rules import PieceKind
from utils.datatypes import StudyPublicity

if TYPE_CHECKING:
    from .player import Player


class StudyBase(SQLModel):
    name: str = Field(max_length=64)
    description: str = Field(max_length=2000)
    publicity: StudyPublicity
    starting_sip: str = SIP_COLUMN
    key_sip: str = SIP_COLUMN


class Study(StudyBase, table=True):
    id: int | None = Field(primary_key=True)
    created_at: datetime = CURRENT_DATETIME_COLUMN
    modified_at: datetime = CURRENT_DATETIME_COLUMN
    author_login: str = Field(foreign_key="player.login")
    deleted: bool = False

    author: "Player" = Relationship(back_populates="studies")
    tags: list["StudyTag"] = Relationship(back_populates="study", cascade_delete=True)
    nodes: list["StudyVariationNode"] = Relationship(back_populates="study", cascade_delete=True)


class StudyTagBase(SQLModel):
    tag: str = Field(primary_key=True, max_length=16)


class StudyTag(StudyTagBase, table=True):
    study_id: int | None = Field(primary_key=True, foreign_key="study.id")

    study: Study = Relationship(back_populates="tags")


class StudyTagPublic(StudyTagBase):
    pass


class StudyVariationNodeBase(SQLModel):
    joined_path: str = Field(primary_key=True, max_length=500)
    ply_from_i: int
    ply_from_j: int
    ply_to_i: int
    ply_to_j: int
    ply_morph_into: PieceKind | None


class StudyVariationNode(StudyVariationNodeBase, table=True):
    study_id: int | None = Field(primary_key=True, foreign_key="study.id")

    study: Study = Relationship(back_populates="nodes")


class StudyVariationNodePublic(StudyVariationNodeBase):
    pass


class StudyCreate(StudyBase):
    tags: list[str]


class StudyUpdate(StudyCreate):
    id: int


class StudyPublic(StudyBase):
    id: int
    created_at: datetime
    modified_at: datetime
    author_login: str
    deleted: bool
    tags: list[StudyTagPublic]
    nodes: list[StudyVariationNodePublic]