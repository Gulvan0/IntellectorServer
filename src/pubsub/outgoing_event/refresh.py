from challenge.samples import active_public_challenges, incoming_challenges, outgoing_challenges
from common.samples import underscore_str, user_ref_with_nickname, user_ref_with_nickname_list
from game.samples import game_state_refreshes, minimal_representative_games
from pubsub.models.channel import (
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
)
from pubsub.models.state import (
    ChallengeListStateRefresh,
    GameListChannelsStateRefresh,
    GameStateRefresh,
    StartedPlayerGamesStateRefresh,
    SubscriberListChannelStateRefresh,
)
from pubsub.outgoing_event.base import RefreshEvent


class StartedPlayerGamesRefresh(RefreshEvent[StartedPlayerGamesStateRefresh, StartedPlayerGamesEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[StartedPlayerGamesStateRefresh]:
        watched_player = user_ref_with_nickname()
        return [
            StartedPlayerGamesStateRefresh(
                current_games=minimal_representative_games(watched_player, finished=False)
            ),
            StartedPlayerGamesStateRefresh(
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
            GameListChannelsStateRefresh(games=minimal_representative_games(finished=False)),
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


class SubscriberListRefresh(RefreshEvent[SubscriberListChannelStateRefresh, SubscriberListEventChannel]):
    @classmethod
    def payload_examples(cls) -> list[SubscriberListChannelStateRefresh]:
        return [
            SubscriberListChannelStateRefresh(subscribers=user_ref_with_nickname_list(3), unauthenticated_subs_count=1),
            SubscriberListChannelStateRefresh(subscribers=user_ref_with_nickname_list(1), unauthenticated_subs_count=0),
            SubscriberListChannelStateRefresh(subscribers=[], unauthenticated_subs_count=6),
        ]
