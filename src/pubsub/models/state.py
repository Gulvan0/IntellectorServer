from typing import Literal
from challenge.models import ChallengePublic
from common.models import UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from game.models.main import Game, GameSummaryPublic, GenericEventList
from game.models.outcome import GameOutcomePublic
from game.models.time_update import GameTimeUpdate, GameTimeUpdatePublic
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

    @classmethod
    def construct_from_game(
        cls,
        game: Game,
        resolved_refs: ResolvedRefs,
        latest_time_update: GameTimeUpdate | None,
        reason: Literal['SUB', 'INVALID_MOVE'],
        include_spectator_messages: bool = True
    ) -> GameStateRefresh:
        return GameStateRefresh(
            refresh_reason=reason,
            outcome=game.outcome.to_public() if game.outcome else None,
            events=game._collect_events(resolved_refs, include_spectator_messages),
            latest_time_update=GameTimeUpdatePublic.cast(latest_time_update)
        )


class SubscriberListChannelStateRefresh(CustomModel):
    subscribers: list[UserRefWithNickname]
    unauthenticated_subs_count: int
