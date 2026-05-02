from typing import Literal
from challenge.models import ChallengePublic
from common.models import UserRefWithNickname
from game.models.main import GameSummaryPublic, GenericEventList
from game.models.outcome import GameOutcomePublic
from game.models.time_update import GameTimeUpdatePublic
from utils.custom_model import CustomModel


class ChallengeListStateRefresh(CustomModel):
    challenges: list[ChallengePublic]


class CurrentGameListStateRefresh(CustomModel):
    games: list[GameSummaryPublic]


class StartedPlayerGamesStateRefresh(CustomModel):
    current_games: list[GameSummaryPublic]


class GameStateRefresh(CustomModel):
    refresh_reason: Literal['SUB', 'INVALID_MOVE']
    outcome: GameOutcomePublic | None
    events: GenericEventList
    latest_time_update: GameTimeUpdatePublic | None


class SubscriberListChannelStateRefresh(CustomModel):
    subscribers: list[UserRefWithNickname]
    unauthenticated_subs_count: int
