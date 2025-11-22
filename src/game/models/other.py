from src.game.models.main import Game
from src.utils.custom_model import CustomModel


class GameListChannelsStateRefresh(CustomModel):
    games: list[Game]


class GameId(CustomModel):
    game_id: int
