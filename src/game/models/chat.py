from sqlmodel import Field, Relationship

from src.common.field_types import CurrentDatetime, PlayerRef
from src.utils.custom_model import CustomSQLModel

import src.game.models.main as game_main_models


class GameChatMessageEventBase(CustomSQLModel):
    occurred_at: CurrentDatetime
    author_ref: PlayerRef
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: game_main_models.Game = Relationship(back_populates="chat_message_events")

    def to_broadcasted_data(self) -> "ChatMessageBroadcastedData":
        return ChatMessageBroadcastedData.cast(self)


class GameChatMessageEventPublic(GameChatMessageEventBase):
    pass


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    game_id: int
