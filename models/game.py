from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlmodel import Field, Relationship, SQLModel, or_

from .column_types import CurrentDatetime, OptionalSip, PlayerRef, Sip, OptionalPlayerRef
from .common import PieceColorField, PieceKindField, PlyKindField
from utils.datatypes import FischerTimeControlEntity, OfferAction, OfferKind, OutcomeKind, TimeControlKind


class GameFilter(BaseModel):
    player_ref: OptionalPlayerRef = None
    time_control_kind: TimeControlKind | None = None

    def construct_conditions(self) -> list[bool | ColumnElement[bool]]:
        conditions: list[bool | ColumnElement[bool]] = []
        if self.player_ref:
            conditions.append(or_(
                Game.white_player_ref == self.player_ref,
                Game.black_player_ref == self.player_ref
            ))
        if self.time_control_kind:
            conditions.append(Game.time_control_kind == self.time_control_kind)
        return conditions


# GAME (MAIN MODELS)


class GameBase(SQLModel):
    started_at: CurrentDatetime

    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: OptionalSip


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


class GameStartDetailsPublic(GameBase):
    id: int

    fischer_time_control: Optional["GameFischerTimeControlPublic"]


class GameEndDetailsPublic(GameBase):
    id: int

    fischer_time_control: Optional["GameFischerTimeControlPublic"]
    outcome: "GameOutcomePublic"
    final_sip: str


# Time Control


class GameFischerTimeControlBase(SQLModel):
    start_seconds: int
    increment_seconds: int = 0


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = GameFischerTimeControlBase


class GameFischerTimeControl(GameFischerTimeControlBase, table=True):
    game_id: int | None = Field(primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="fischer_time_control")


class GameFischerTimeControlPublic(GameFischerTimeControlBase):
    pass


# Outcome


class GameOutcomeBase(SQLModel):
    game_ended_at: CurrentDatetime
    kind: OutcomeKind
    winner: PieceColorField


class GameOutcome(GameOutcomeBase, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="outcome")


class GameOutcomePublic(GameOutcomeBase):
    pass


# Ply


class GamePlyEventBase(SQLModel):
    occurred_at: CurrentDatetime
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
    sip_after: Sip

    game: Game = Relationship(back_populates="ply_events")


class HistoricalGamePlyEventPublic(GamePlyEventBase):  # Used in ply history
    pass


class MessageGamePlyEventPublic(GamePlyEventBase):  # Broadcasted when a new move happens
    game_id: int
    sip_after: str


# Chat


class GameChatMessageEventBase(SQLModel):
    occurred_at: CurrentDatetime
    author_ref: PlayerRef
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
    occurred_at: CurrentDatetime
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
    occurred_at: CurrentDatetime
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
    occurred_at: CurrentDatetime
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
