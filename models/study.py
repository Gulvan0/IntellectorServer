from datetime import datetime
from typing import Any, Self, TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from .common import PieceKindField, VariationNode
from .utils import CURRENT_DATETIME_COLUMN, SIP_COLUMN
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
    ply_morph_into: PieceKindField | None = None


class StudyVariationNode(StudyVariationNodeBase, table=True):
    study_id: int | None = Field(primary_key=True, foreign_key="study.id")

    study: Study = Relationship(back_populates="nodes")

    @classmethod
    def from_api_model(cls, node: VariationNode) -> Self:
        return StudyVariationNode(
            joined_path=node.path,
            ply_from_i=node.ply.departure.i,
            ply_from_j=node.ply.departure.j,
            ply_to_i=node.ply.destination.i,
            ply_to_j=node.ply.destination.j,
            ply_morph_into=node.ply.morph_into
        )


class StudyVariationNodePublic(StudyVariationNodeBase):
    pass


class StudyCreate(StudyBase):
    tags: list[str]
    nodes: list[VariationNode]

    def build_table_model(self, author_login: str) -> Study:
        return Study(
            author_login=author_login,
            tags=[
                StudyTag(tag=tag)
                for tag in self.tags
            ],
            nodes=[
                StudyVariationNode.from_api_model(node)
                for node in self.nodes
            ],
            **StudyBase.model_validate(self).model_dump()
        )


class StudyUpdate(SQLModel):
    name: str | None = Field(max_length=64, default=None)
    description: str | None = Field(max_length=2000, default=None)
    publicity: StudyPublicity | None = None
    starting_sip: str | None = None
    key_sip: str | None = None
    tags: list[str] | None = None
    nodes: list[VariationNode] | None = None

    def dump_for_table_model(self) -> dict[str, Any]:
        result = self.model_dump(exclude_unset=True)

        result.pop("tags", None)
        if self.tags is not None:
            result["tags"] = [
                StudyTag(tag=tag)
                for tag in self.tags
            ]

        result.pop("nodes", None)
        if self.nodes is not None:
            result["nodes"] = [
                StudyVariationNode.from_api_model(node)
                for node in self.nodes
            ]

        return result


class StudyPublic(StudyBase):
    id: int
    created_at: datetime
    modified_at: datetime
    author_login: str
    deleted: bool
    tags: list[StudyTagPublic]
    nodes: list[StudyVariationNodePublic]