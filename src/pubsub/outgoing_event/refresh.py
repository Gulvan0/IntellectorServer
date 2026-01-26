from src.challenge.models import ChallengeListStateRefresh
from src.challenge.samples import active_public_challenges, incoming_challenges, outgoing_challenges
from src.common.samples import underscore_str, user_ref_with_nickname, user_ref_with_nickname_list
from src.game.models.main import GameStateRefresh
from src.game.models.other import GameListChannelsStateRefresh
from src.game.samples import game_state_refreshes, minimal_representative_games
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


class StartedPlayerGamesRefresh(RefreshEvent[StartedPlayerGamesStateRefresh, StartedPlayerGamesEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[StartedPlayerGamesStateRefresh]:
        watched_player = user_ref_with_nickname()
        return [
            StartedPlayerGamesStateRefresh(
                player_ref=watched_player.user_ref,
                current_games=minimal_representative_games(watched_player)
            ),
            StartedPlayerGamesStateRefresh(
                player_ref=underscore_str(),
                current_games=[]
            ),
        ]


class PublicChallengeListRefresh(RefreshEvent[ChallengeListStateRefresh, PublicChallengeListEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[ChallengeListStateRefresh]:
        return [
            ChallengeListStateRefresh(challenges=active_public_challenges(3)),
            ChallengeListStateRefresh(challenges=active_public_challenges(1)),
            ChallengeListStateRefresh(challenges=[]),
        ]


class GameListRefresh(RefreshEvent[GameListChannelsStateRefresh, GameListEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[GameListChannelsStateRefresh]:
        return [
            GameListChannelsStateRefresh(games=minimal_representative_games()),
            GameListChannelsStateRefresh(games=[]),
        ]


class IncomingChallengesRefresh(RefreshEvent[ChallengeListStateRefresh, IncomingChallengesEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[ChallengeListStateRefresh]:
        return [
            ChallengeListStateRefresh(challenges=incoming_challenges(3)),
            ChallengeListStateRefresh(challenges=incoming_challenges(1)),
            ChallengeListStateRefresh(challenges=[]),
        ]


class OutgoingChallengesRefresh(RefreshEvent[ChallengeListStateRefresh, OutgoingChallengesEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[ChallengeListStateRefresh]:
        sample_challenges = outgoing_challenges(4)
        return [
            ChallengeListStateRefresh(challenges=sample_challenges[:3]),
            ChallengeListStateRefresh(challenges=[sample_challenges[3]]),
            ChallengeListStateRefresh(challenges=[]),
        ]


class GameRefresh(RefreshEvent[GameStateRefresh, GameEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[GameStateRefresh]:
        return game_state_refreshes()


class SubscriberListRefresh(RefreshEvent[SubscriberListEventChannelState, SubscriberListEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[SubscriberListEventChannelState]:
        return [
            SubscriberListEventChannelState(subscribers=user_ref_with_nickname_list(3)),
            SubscriberListEventChannelState(subscribers=user_ref_with_nickname_list(1)),
            SubscriberListEventChannelState(subscribers=[]),
        ]
