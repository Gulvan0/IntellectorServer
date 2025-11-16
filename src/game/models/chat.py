from sqlmodel import Field, Relationship, SQLModel

from src.common.field_types import CurrentDatetime, PlayerRef

import src.game.models.main as game_main_models


class GameChatMessageEventBase(SQLModel):
    occurred_at: CurrentDatetime
    author_ref: PlayerRef
    text: str
    spectator: bool


class GameChatMessageEvent(GameChatMessageEventBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")

    game: game_main_models.Game = Relationship(back_populates="chat_message_events")


class GameChatMessageEventPublic(GameChatMessageEventBase):
    pass


class ChatMessageBroadcastedData(GameChatMessageEventBase):
    game_id: int
