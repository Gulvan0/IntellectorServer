from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN, SIP_COLUMN
from .common import PieceColorField, PieceKindField, PlyKindField
from utils.datatypes import OfferAction, OfferKind, OutcomeKind, TimeControlKind



class Game(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    started_at: datetime = CURRENT_DATETIME_COLUMN
    white_player_ref: str = PLAYER_REF_COLUMN
    black_player_ref: str = PLAYER_REF_COLUMN
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: str | None = SIP_COLUMN

    fischer_time_control: Optional["GameFischerTimeControl"] = Relationship(back_populates="game", cascade_delete=True)
    outcome: Optional["GameOutcome"] = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list["GamePlyEvent"] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list["GameChatMessageEvent"] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list["GameOfferEvent"] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list["GameTimeAddedEvent"] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list["GameRollbackEvent"] = Relationship(back_populates="game", cascade_delete=True)


class GameFischerTimeControl(SQLModel, table=True):
    game_id: int | None = Field(primary_key=True, foreign_key="game.id")
    start_seconds: int
    increment_seconds: int = 0

    game: Game = Relationship(back_populates="fischer_time_control")


class GameOutcome(SQLModel, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")
    game_ended_at: datetime = CURRENT_DATETIME_COLUMN
    kind: OutcomeKind
    winner: PieceColorField

    game: Game = Relationship(back_populates="outcome")


class GamePlyEvent(SQLModel, table=True):  # Analytics-optimized
    id: int | None = Field(primary_key=True)
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    game_id: int = Field(foreign_key="game.id")
    ply_index: int
    is_cancelled: bool = False
    moving_color: PieceColorField
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    kind: PlyKindField
    morph_into: PieceKindField | None
    moved_piece: PieceKindField
    target_piece: PieceKindField | None
    sip_after: str | None = SIP_COLUMN

    game: Game = Relationship(back_populates="ply_events")


class GameChatMessageEvent(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    game_id: int = Field(foreign_key="game.id")
    author_ref: str = PLAYER_REF_COLUMN
    text: str
    spectator: bool

    game: Game = Relationship(back_populates="chat_message_events")


class GameOfferEvent(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    game_id: int = Field(foreign_key="game.id")
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColorField

    game: Game = Relationship(back_populates="offer_events")


class GameTimeAddedEvent(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    game_id: int = Field(foreign_key="game.id")
    amount_seconds: int
    receiver: PieceColorField

    game: Game = Relationship(back_populates="time_added_events")


class GameRollbackEvent(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    game_id: int = Field(foreign_key="game.id")
    position_index_before: int
    position_index_after: int
    requested_by: PieceColorField

    game: Game = Relationship(back_populates="rollback_events")