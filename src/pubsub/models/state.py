from typing import Literal
from src.challenge.models import ChallengePublic
from src.common.models import UserRefWithNickname
from src.game.models.main import GamePublic, GenericEventList
from src.game.models.outcome import GameOutcomePublic
from src.game.models.time_update import GameTimeUpdatePublic
from src.utils.custom_model import CustomModel


class ChallengeListStateRefresh(CustomModel):
    challenges: list[ChallengePublic]


class GameListChannelsStateRefresh(CustomModel):
    games: list[GamePublic]


class StartedPlayerGamesStateRefresh(CustomModel):
    player_ref: str
    current_games: list[GamePublic]


class GameStateRefresh(CustomModel):
    game_id: int
    refresh_reason: Literal['sub', 'invalid_move']
    outcome: GameOutcomePublic | None
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


class SubscriberListChannelStateRefresh(CustomModel):
    subscribers: list[UserRefWithNickname]
    unauthenticated_subs_count: int
