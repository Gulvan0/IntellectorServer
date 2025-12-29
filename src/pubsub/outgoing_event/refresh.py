from datetime import datetime, UTC
from src.challenge.models import ChallengeListStateRefresh
from src.game.datatypes import OutcomeKind
from src.game.models.main import GameStateRefresh
from src.game.models.other import GameListChannelsStateRefresh
from src.game.models.outcome import GameOutcomePublic
from src.game.models.time_update import GameTimeUpdatePublic, GameTimeUpdateReason
from src.player.models import StartedPlayerGamesStateRefresh
from src.pubsub.models.channel import (
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
)
from src.pubsub.models.state import SubscriberListEventChannelState
from src.pubsub.outgoing_event.base import RefreshEvent
from src.rules import PieceColor


class StartedPlayerGamesRefresh(RefreshEvent[StartedPlayerGamesStateRefresh, StartedPlayerGamesEventChannel]):
    @classmethod
    def payload_example(cls) -> StartedPlayerGamesStateRefresh:
        return StartedPlayerGamesStateRefresh(
            player_ref="watched_player_login",
            current_games=[]  # TODO: Fill the list with game samples
        )


class PublicChallengeListRefresh(RefreshEvent[ChallengeListStateRefresh, PublicChallengeListEventChannel]):
    @classmethod
    def payload_example(cls) -> ChallengeListStateRefresh:
        return ChallengeListStateRefresh(
            challenges=[]  # TODO: Fill the list with challenge samples
        )


class GameListRefresh(RefreshEvent[GameListChannelsStateRefresh, GameListEventChannel]):
    @classmethod
    def payload_example(cls) -> GameListChannelsStateRefresh:
        return GameListChannelsStateRefresh(
            games=[]  # TODO: Fill the list with game samples
        )


class IncomingChallengesRefresh(RefreshEvent[ChallengeListStateRefresh, IncomingChallengesEventChannel]):
    @classmethod
    def payload_example(cls) -> ChallengeListStateRefresh:
        return ChallengeListStateRefresh(
            challenges=[]  # TODO: Fill the list with challenge samples
        )


class OutgoingChallengesRefresh(RefreshEvent[ChallengeListStateRefresh, OutgoingChallengesEventChannel]):
    @classmethod
    def payload_example(cls) -> ChallengeListStateRefresh:
        return ChallengeListStateRefresh(
            challenges=[]  # TODO: Fill the list with challenge samples
        )


class GameRefresh(RefreshEvent[GameStateRefresh, GameEventChannel]):
    @classmethod
    def payload_example(cls) -> GameStateRefresh:
        return GameStateRefresh(  # TODO: Replace field values with imported examples
            game_id=123,
            refresh_reason='invalid_move',
            outcome=GameOutcomePublic(
                kind=OutcomeKind.RESIGN,
                winner=PieceColor.BLACK,
                time_update=GameTimeUpdatePublic(
                    updated_at=datetime.now(UTC),
                    white_ms=180000,
                    black_ms=180000,
                    ticking_side=None,
                    reason=GameTimeUpdateReason.GAME_ENDED
                )
            ),
            events=[],
            latest_time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.GAME_ENDED
            )
        )


class SubscriberListRefresh(RefreshEvent[SubscriberListEventChannelState, SubscriberListEventChannel]):
    @classmethod
    def payload_example(cls) -> SubscriberListEventChannelState:
        return SubscriberListEventChannelState(
            subscribers=[]  # TODO: Fill with examples
        )
