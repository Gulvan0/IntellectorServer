from sqlmodel import Field, Relationship

from src.common.field_types import CurrentDatetime, PlayerRef
from src.common.models import UserRefWithNickname
from src.utils.async_orm_session import AsyncSession
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models
import src.player.methods as player_methods


class GameChatMessageEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    author_ref: PlayerRef
    game_id: int = Field(foreign_key="game.id")

    game: game_main_models.Game = Relationship(back_populates="chat_message_events")

    async def to_broadcasted_data(self, session: AsyncSession) -> "ChatMessageBroadcastedData":
        return ChatMessageBroadcastedData(
            occurred_at=self.occurred_at,
            text=self.text,
            spectator=self.spectator,
            author=await player_methods.get_user_ref_with_nickname(session, self.author_ref),
            game_id=self.game_id
        )

    async def to_public(self, session: AsyncSession) -> "GameChatMessageEventPublic":
        return GameChatMessageEventPublic(
            occurred_at=self.occurred_at,
            text=self.text,
            spectator=self.spectator,
            author=await player_methods.get_user_ref_with_nickname(session, self.author_ref)
        )


class GameChatMessageEventPublic(GameChatMessageEventBase):
    author: UserRefWithNickname


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    author: UserRefWithNickname
    game_id: int
