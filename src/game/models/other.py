from pydantic import BaseModel

from src.game.models.main import Game


class GameListChannelsStateRefresh(BaseModel):
    games: list[Game]


class GameId(BaseModel):
    game_id: int
