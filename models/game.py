from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN, SIP_COLUMN
from .common import PieceColorField, PieceKindField, PlyKindField
from utils.datatypes import FischerTimeControlEntity, OfferAction, OfferKind, OutcomeKind, TimeControlKind


# GAME (MAIN MODELS)


class GameBase(SQLModel):
    started_at: datetime = CURRENT_DATETIME_COLUMN

    white_player_ref: str = PLAYER_REF_COLUMN
    black_player_ref: str = PLAYER_REF_COLUMN
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: str | None = SIP_COLUMN


class Game(GameBase, table=True):
    id: int | None = Field(primary_key=True)

    fischer_time_control: Optional["GameFischerTimeControl"] = Relationship(back_populates="game", cascade_delete=True)
    outcome: Optional["GameOutcome"] = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list["GamePlyEvent"] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list["GameChatMessageEvent"] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list["GameOfferEvent"] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list["GameTimeAddedEvent"] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list["GameRollbackEvent"] = Relationship(back_populates="game", cascade_delete=True)


class GamePublic(GameBase):
    id: int

    fischer_time_control: Optional["GameFischerTimeControlPublic"]
    outcome: Optional["GameOutcomePublic"]
    ply_events: list["HistoricalGamePlyEventPublic"]
    chat_message_events: list["HistoricalGameChatMessageEventPublic"]
    offer_events: list["HistoricalGameOfferEventPublic"]
    time_added_events: list["HistoricalGameTimeAddedEventPublic"]
    rollback_events: list["HistoricalGameRollbackEventPublic"]


# Time Control


class GameFischerTimeControlBase(SQLModel, FischerTimeControlEntity):
    start_seconds: int
    increment_seconds: int = 0


class GameFischerTimeControl(GameFischerTimeControlBase, FischerTimeControlEntity, table=True):
    game_id: int | None = Field(primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="fischer_time_control")


class GameFischerTimeControlPublic(GameFischerTimeControlBase, FischerTimeControlEntity):
    pass


# Outcome


class GameOutcomeBase(SQLModel):
    game_ended_at: datetime = CURRENT_DATETIME_COLUMN
    kind: OutcomeKind
    winner: PieceColorField


class GameOutcome(GameOutcomeBase, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="outcome")


class GameOutcomePublic(GameOutcomeBase):
    pass


# Ply


class GamePlyEventBase(SQLModel):
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    ply_index: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKindField | None


class GamePlyEvent(GamePlyEventBase, table=True):  # Analytics-optimized
    id: int | None = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    is_cancelled: bool = False
    kind: PlyKindField
    moving_color: PieceColorField
    moved_piece: PieceKindField
    target_piece: PieceKindField | None
    sip_after: str = SIP_COLUMN

    game: Game = Relationship(back_populates="ply_events")


class HistoricalGamePlyEventPublic(GamePlyEventBase):  # Used in ply history
    pass


class MessageGamePlyEventPublic(GamePlyEventBase):  # Broadcasted when a new move happens
    game_id: int
    sip_after: str


# Chat


class GameChatMessageEventBase(SQLModel):
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    author_ref: str = PLAYER_REF_COLUMN
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="chat_message_events")


class HistoricalGameChatMessageEventPublic(GameChatMessageEventBase):  # Used in chat log
    pass


class MessageGameChatMessagePlyEventPublic(GameChatMessageEventBase):  # Broadcasted when a new message arrives
    game_id: int


# Offer


class GameOfferEventBase(SQLModel):
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColorField


class GameOfferEvent(GameOfferEventBase, table=True):
    id: int | None = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="offer_events")


class HistoricalGameOfferEventPublic(GameOfferEventBase):
    pass


class MessageGameOfferEventPublic(GameOfferEventBase):
    game_id: int


# Time Added


class GameTimeAddedEventBase(SQLModel):
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    amount_seconds: int
    receiver: PieceColorField


class GameTimeAddedEvent(GameTimeAddedEventBase, table=True):
    id: int | None = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="time_added_events")


class HistoricalGameTimeAddedEventPublic(GameTimeAddedEventBase):
    pass


class MessageGameTimeAddedEventPublic(GameTimeAddedEventBase):
    game_id: int


# Rollback


class GameRollbackEventBase(SQLModel):
    occurred_at: datetime = CURRENT_DATETIME_COLUMN
    position_index_before: int
    position_index_after: int
    requested_by: PieceColorField


class GameRollbackEvent(GameRollbackEventBase, table=True):
    id: int | None = Field(primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="rollback_events")


class HistoricalGameRollbackEventPublic(GameRollbackEventBase):
    pass


class MessageGameRollbackEventPublic(GameRollbackEventBase):
    game_id: int
