from typing import Literal, Optional

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

from src.common.field_types import CurrentDatetime, OptionalSip, PlayerRef, OptionalPlayerRef
from src.common.time_control import TimeControlKind
from src.game.models.time_control import GameFischerTimeControl, GameFischerTimeControlPublic
from src.game.models.outcome import GameOutcome, GameOutcomePublic
from src.game.models.ply import GamePlyEvent, GamePlyEventPublic
from src.game.models.chat import GameChatMessageEvent, GameChatMessageEventPublic
from src.game.models.offer import GameOfferEvent, GameOfferEventPublic
from src.game.models.rollback import GameRollbackEvent, GameRollbackEventPublic
from src.game.models.time_added import GameTimeAddedEvent, GameTimeAddedEventPublic
from src.game.models.time_update import GameTimeUpdatePublic


GenericEventList = list[GamePlyEventPublic | GameChatMessageEventPublic | GameOfferEventPublic | GameTimeAddedEventPublic | GameRollbackEventPublic]


class GameBase(SQLModel):
    started_at: CurrentDatetime

    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: OptionalSip
    external_uploader_ref: OptionalPlayerRef


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    fischer_time_control: Optional[GameFischerTimeControl] = Relationship(back_populates="game", cascade_delete=True)
    outcome: Optional[GameOutcome] = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list[GamePlyEvent] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list[GameChatMessageEvent] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list[GameOfferEvent] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list[GameTimeAddedEvent] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list[GameRollbackEvent] = Relationship(back_populates="game", cascade_delete=True)


class GamePublic(GameBase):
    id: int

    fischer_time_control: Optional[GameFischerTimeControlPublic]
    outcome: Optional[GameOutcomePublic]
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


class GameStartedBroadcastedData(GameBase):
    id: int
    fischer_time_control: GameFischerTimeControlPublic | None


class GameStateRefresh(BaseModel):
    game_id: int
    refresh_reason: Literal['sub', 'invalid_move']
    outcome: GameOutcomePublic | None
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None
