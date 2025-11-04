# flake8: noqa
# mypy: ignore-errors
from pydantic import BaseModel
from .chat import *
from .incoming_ws import *
from .main import *
from .offer import *
from .outcome import *
from .ply import *
from .rest import *
from .rollback import *
from .time_added import *
from .time_control import *
from .time_update import *


class GameListChannelsStateRefresh(BaseModel):
    games: list[Game]


class GameId(BaseModel):
    game_id: int
