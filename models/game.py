from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel
from sqlalchemy import ColumnElement
from sqlmodel import Field, Relationship, SQLModel, or_

from .column_types import CurrentDatetime, OptionalSip, PlayerRef, Sip, OptionalPlayerRef
from .common import PieceColorField, PieceKindField, PlyKindField
from utils.datatypes import FischerTimeControlEntity, OfferAction, OfferKind, OutcomeKind, TimeControlKind


# GAME (MAIN MODELS)


class GameBase(SQLModel):
    started_at: CurrentDatetime

    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: OptionalSip


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    vk_announcement_message_id: int | None = None

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
    ply_events: list["GamePlyEventPublic"]
    chat_message_events: list["GameChatMessageEventPublic"]
    offer_events: list["GameOfferEventPublic"]
    time_added_events: list["GameTimeAddedEventPublic"]
    rollback_events: list["GameRollbackEventPublic"]


# Time Control


class GameFischerTimeControlBase(SQLModel):
    start_seconds: int
    increment_seconds: int = 0


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = GameFischerTimeControlBase


class GameFischerTimeControl(GameFischerTimeControlBase, table=True):
    game_id: int | None = Field(default=None, primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="fischer_time_control")


class GameFischerTimeControlPublic(GameFischerTimeControlBase):
    pass


# Outcome


class GameOutcomeBase(SQLModel):
    game_ended_at: CurrentDatetime
    kind: OutcomeKind
    winner: PieceColorField | None = None
    final_white_seconds: int | None = None
    final_black_seconds: int | None = None


class GameOutcome(GameOutcomeBase, table=True):
    game_id: int = Field(primary_key=True, foreign_key="game.id")

    game: Game = Relationship(back_populates="outcome")


class GameOutcomePublic(GameOutcomeBase):
    pass


# Ply


class GamePlyEventBase(SQLModel):
    occurred_at: CurrentDatetime
    ply_index: int
    white_seconds_after_execution: int | None = None
    black_seconds_after_execution: int | None = None
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKindField | None = None


class GamePlyEvent(GamePlyEventBase, table=True):  # Analytics-optimized
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    is_cancelled: bool = False
    kind: PlyKindField
    moving_color: PieceColorField
    moved_piece: PieceKindField
    target_piece: PieceKindField | None = None
    sip_after: Sip

    game: Game = Relationship(back_populates="ply_events")


class GamePlyEventPublic(GamePlyEventBase):
    pass


# Chat


class GameChatMessageEventBase(SQLModel):
    occurred_at: CurrentDatetime
    author_ref: PlayerRef
    text: str


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    spectator: bool

    game: Game = Relationship(back_populates="chat_message_events")


class GameChatMessageEventPublic(GameChatMessageEventBase):
    spectator: bool


# Offer


class GameOfferEventBase(SQLModel):
    occurred_at: CurrentDatetime
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColorField


class GameOfferEvent(GameOfferEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="offer_events")


class GameOfferEventPublic(GameOfferEventBase):
    pass


# Time Added


class GameTimeAddedEventBase(SQLModel):
    occurred_at: CurrentDatetime
    amount_seconds: int
    receiver: PieceColorField


class GameTimeAddedEvent(GameTimeAddedEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="time_added_events")


class GameTimeAddedEventPublic(GameTimeAddedEventBase):
    pass


# Rollback


class GameRollbackEventBase(SQLModel):
    occurred_at: CurrentDatetime
    position_index_before: int
    position_index_after: int
    requested_by: PieceColorField


class GameRollbackEvent(GameRollbackEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="rollback_events")


class GameRollbackEventPublic(GameRollbackEventBase):
    pass


# REST payloads / payload fields


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


# WS payloads / payload fields - incoming


class PlyIntentData(BaseModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKindField | None = None
    sip_after: Sip


class ChatMessageIntentData(BaseModel):
    game_id: int
    text: str


class OfferActionIntentData(BaseModel):
    game_id: int
    action_kind: OfferAction
    offer_kind: OfferKind


class AddTimeIntentData(BaseModel):
    game_id: int


# WS payloads / payload fields - outgoing


class GameStartedBroadcastedData(GameBase):
    id: int
    fischer_time_control: GameFischerTimeControlPublic | None


class PlyBroadcastedData(GamePlyEventBase):
    game_id: int
    sip_after: Sip


class InvalidPlyResponseData(BaseModel):
    game_id: int
    ply_history: list[GamePlyEventPublic]
    current_sip: Sip


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    game_id: int


class OfferActionBroadcastedData(BaseModel):
    game_id: int
    occurred_at: CurrentDatetime
    action: OfferAction
    offer_kind: OfferKind
    offer_author: PieceColorField


class TimeAddedBroadcastedData(GameTimeAddedEventBase):
    game_id: int
    updated_receiver_seconds: int


class GameEndedBroadcastedData(GameOutcomeBase):
    game_id: int


class RollbackBroadcastedData(BaseModel):
    game_id: int
    updated_white_seconds: int | None = None
    updated_black_seconds: int | None = None
    updated_sip: Sip
    updated_move_num: int
