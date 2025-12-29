from src.utils.custom_model import CustomModel

import src.game.models.main as main_game_models


class GameListChannelsStateRefresh(CustomModel):
    games: list[main_game_models.GamePublic]


class GameId(CustomModel):
    game_id: int
