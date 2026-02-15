from typing import TYPE_CHECKING, Literal
from sqlmodel import Field, Relationship

from common.field_types import CurrentDatetime, PlayerRef
from common.models import UserRefWithNickname
from game.datatypes import EventKind
from player.methods import get_user_ref_with_nickname
from utils.async_orm_session import AsyncSession
from utils.custom_model import CustomModel, CustomSQLModel


if TYPE_CHECKING:
    from game.models.main import Game


class GameChatMessageEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    author_ref: PlayerRef
    game_id: int = Field(foreign_key="game.id")

    game: Game = Relationship(back_populates="chat_message_events")

    async def to_broadcasted_data(self, session: AsyncSession) -> ChatMessageBroadcastedData:
        return ChatMessageBroadcastedData(
            occurred_at=self.occurred_at,
            text=self.text,
            spectator=self.spectator,
            author=await get_user_ref_with_nickname(session, self.author_ref),
            game_id=self.game_id
        )

    async def to_public(self, session: AsyncSession) -> GameChatMessageEventPublic:
        return GameChatMessageEventPublic(
            occurred_at=self.occurred_at,
            text=self.text,
            spectator=self.spectator,
            author=await get_user_ref_with_nickname(session, self.author_ref)
        )


class GameChatMessageEventPublic(GameChatMessageEventBase):
    event_kind: Literal[EventKind.CHAT_MESSAGE] = EventKind.CHAT_MESSAGE
    author: UserRefWithNickname


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    author: UserRefWithNickname
    game_id: int


class GameSendChatMessagePayload(CustomModel):
    game_id: int
    text: str
