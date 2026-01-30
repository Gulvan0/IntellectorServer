from typing import Optional
from sqlmodel import Field, Relationship

from common.field_types import CurrentDatetime, OptionalSip, PlayerRef, OptionalPlayerRef
from common.models import UserRefWithNickname
from common.time_control import TimeControlKind
from game.models.time_control import GameFischerTimeControl, GameFischerTimeControlPublic
from game.models.outcome import GameOutcome, GameOutcomePublic
from game.models.ply import GamePlyEvent, GamePlyEventPublic
from game.models.chat import GameChatMessageEvent, GameChatMessageEventPublic
from game.models.offer import GameOfferEvent, GameOfferEventPublic
from game.models.rollback import GameRollbackEvent, GameRollbackEventPublic
from game.models.time_added import GameTimeAddedEvent, GameTimeAddedEventPublic
from game.models.time_update import GameTimeUpdatePublic
from utils.custom_model import CustomSQLModel


GenericEventList = list[GamePlyEventPublic | GameChatMessageEventPublic | GameOfferEventPublic | GameTimeAddedEventPublic | GameRollbackEventPublic]


class GameBase(CustomSQLModel):
    started_at: CurrentDatetime

    time_control_kind: TimeControlKind
    rated: bool
    custom_starting_sip: OptionalSip
    external_uploader_ref: OptionalPlayerRef


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    white_player_ref: PlayerRef
    black_player_ref: PlayerRef

    fischer_time_control: Optional[GameFischerTimeControl] = Relationship(back_populates="game", cascade_delete=True)
    outcome: Optional[GameOutcome] = Relationship(back_populates="game", cascade_delete=True)
    ply_events: list[GamePlyEvent] = Relationship(back_populates="game", cascade_delete=True)
    chat_message_events: list[GameChatMessageEvent] = Relationship(back_populates="game", cascade_delete=True)
    offer_events: list[GameOfferEvent] = Relationship(back_populates="game", cascade_delete=True)
    time_added_events: list[GameTimeAddedEvent] = Relationship(back_populates="game", cascade_delete=True)
    rollback_events: list[GameRollbackEvent] = Relationship(back_populates="game", cascade_delete=True)


class GamePublic(GameBase):
    id: int
    white_player: UserRefWithNickname
    black_player: UserRefWithNickname

    fischer_time_control: Optional[GameFischerTimeControlPublic]
    outcome: Optional[GameOutcomePublic]
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


class GameStartedBroadcastedData(GameBase):
    id: int
    white_player: UserRefWithNickname
    black_player: UserRefWithNickname

    fischer_time_control: GameFischerTimeControlPublic | None
