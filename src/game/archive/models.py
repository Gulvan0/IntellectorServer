from datetime import datetime
from enum import StrEnum, auto
from typing import Annotated, Any

from pydantic import StringConstraints
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field

from common.field_types import current_datetime_field
from common.models import UserRefWithNickname
from common.time_control import TimeControlKind
from board.piece import PieceColor
from game.archive.constants import MAX_PAGE_SIZE, MAX_SORT_LEVELS, SAVED_FILTER_NAME_PATTERN
from game.archive.query import SortColumn
from game.datatypes import OutcomeKind
from game.models.main import PlayerRatingPublic
from utils.custom_model import CustomModel, CustomSQLModel


SavedFilterName = Annotated[str, StringConstraints(strip_whitespace=True, pattern=SAVED_FILTER_NAME_PATTERN)]


class SavedGameFilter(CustomSQLModel, table=True):
    """A user's filter is unique by (author, name), names compared as the DB's collation does: case- and accent-insensitively.
    Authorless filters are managed by the server and are linked by their fixed `key`"""
    __table_args__ = (UniqueConstraint("author_login", "name", name="uq_saved_filter_author_name"),)

    id: int | None = Field(default=None, primary_key=True)
    author_login: str | None = Field(default=None, foreign_key="player.login")
    key: str | None = Field(default=None, max_length=32, unique=True)
    name: str = Field(max_length=32)
    formula: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = current_datetime_field()
    updated_at: datetime = current_datetime_field()


class SavedFilterPublic(CustomModel):
    id: int
    key: str | None
    name: str
    author: UserRefWithNickname | None
    formula: dict[str, Any]


class SavedFilterSummary(CustomModel):
    id: int
    name: str


class SaveFilterPayload(CustomModel):
    name: SavedFilterName
    formula: dict[str, Any]
    overwrite: bool = False


class SortLevelPayload(CustomModel):
    column: SortColumn
    descending: bool = False


class ArchiveSearchPayload(CustomModel):
    formula: dict[str, Any]  # with DateTime operands resolved into instants
    sort: Annotated[list[SortLevelPayload], Field(max_length=MAX_SORT_LEVELS)] = []
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)


class ArchiveColumn(StrEnum):
    """The result table's columns, as the client's column toggles and the export name them"""
    ID = auto()
    LINK = auto()
    WHITE = auto()
    BLACK = auto()
    WHITE_ELO = auto()
    BLACK_ELO = auto()
    STARTED_AT = auto()
    ENDED_AT = auto()
    DURATION = auto()
    TIME_CONTROL = auto()
    START_TIME = auto()
    BONUS_TIME = auto()
    RATED = auto()
    STARTING_POSITION = auto()
    RESULT = auto()
    OUTCOME = auto()
    OPENING = auto()
    MOVE_COUNT = auto()
    TIME_LEFT_WHITE = auto()
    TIME_LEFT_BLACK = auto()


class ArchiveExportPayload(CustomModel):
    formula: dict[str, Any]
    sort: Annotated[list[SortLevelPayload], Field(max_length=MAX_SORT_LEVELS)] = []
    columns: Annotated[list[ArchiveColumn], Field(min_length=1)]  # in the table's order
    include_moves: bool = False
    locale: str = "en"
    timezone: str = "UTC"  # IANA


class ArchiveGameRow(CustomModel):
    id: int
    white_player: UserRefWithNickname
    black_player: UserRefWithNickname
    white_rating: PlayerRatingPublic | None
    black_rating: PlayerRatingPublic | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    time_control_kind: TimeControlKind
    start_seconds: int | None
    increment_seconds: int | None
    rated: bool
    custom_starting_sip: str | None
    opening_id: int | None
    ended: bool
    outcome_kind: OutcomeKind | None
    winner: PieceColor | None
    move_count: int
    white_time_left_ms: int | None
    black_time_left_ms: int | None


class ArchiveSearchResult(CustomModel):
    games: list[ArchiveGameRow]
    total: int
