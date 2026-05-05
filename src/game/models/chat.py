from typing import TYPE_CHECKING, Literal
from sqlmodel import Field, Relationship

from common.field_types import CurrentDatetime, PlayerRef
from common.models import UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from game.datatypes import EventKind
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameChatMessageEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    event_index: int
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    author_ref: PlayerRef
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="chat_message_events")

    def to_broadcasted_data(self, resolved_refs: ResolvedRefs) -> ChatMessageBroadcastedData:
        return ChatMessageBroadcastedData(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            text=self.text,
            spectator=self.spectator,
            author=resolved_refs.get(self.author_ref)
        )

    def to_public(self, resolved_refs: ResolvedRefs) -> GameChatMessageEventPublic:
        return GameChatMessageEventPublic(
            occurred_at=self.occurred_at,
            event_index=self.event_index,
            text=self.text,
            spectator=self.spectator,
            author=resolved_refs.get(self.author_ref)
        )


class GameChatMessageEventPublic(GameChatMessageEventBase):
    event_kind: Literal[EventKind.CHAT_MESSAGE] = EventKind.CHAT_MESSAGE
    author: UserRefWithNickname


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    author: UserRefWithNickname


class GameSendChatMessagePayload(CustomModel):
    game_id: int
    text: str
