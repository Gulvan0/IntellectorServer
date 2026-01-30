
from challenge.models import ChallengePublic
from challenge.samples import incoming_challenges, minimal_representative_challenges
from common.models import Id, IdList, UserRefWithNickname
from common.samples import user_ref_with_nickname
from game.models.chat import ChatMessageBroadcastedData
from game.models.main import GamePublic, GameStartedBroadcastedData
from game.models.offer import OfferActionBroadcastedData
from game.models.outcome import GameEndedBroadcastedData
from game.models.ply import PlyBroadcastedData
from game.models.rollback import RollbackBroadcastedData
from game.models.time_added import TimeAddedBroadcastedData
from game.samples import (
    chat_message_broadcasted_data,
    game_ended_data_samples,
    game_started_data_samples,
    minimal_representative_games,
    offer_action_broadcasted_data,
    ply_broadcasted_data,
    rollback_broadcasted_data,
    time_added_broadcasted_data,
)
from pubsub.models.channel import (
    EveryoneEventChannel,
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
)
from pubsub.outgoing_event.base import OutgoingEvent


# TODO: Make foreign imports absolute (after examples are moved) - in every new module


class ServerShutdown(OutgoingEvent[None, EveryoneEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever the server starts preparing for the shutdown"


class GameStarted(OutgoingEvent[GamePublic, StartedPlayerGamesEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Started (for player's followers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new game involving a player starts"

    @classmethod
    def payload_examples(cls) -> list[GamePublic]:
        return minimal_representative_games()


class NewPublicChallenge(OutgoingEvent[ChallengePublic, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new public challenge is created"

    @classmethod
    def payload_examples(cls) -> list[ChallengePublic]:
        return minimal_representative_challenges()


class PublicChallengeCancelled(OutgoingEvent[Id, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a public challenge is cancelled"


class PublicChallengeFulfilled(OutgoingEvent[Id, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a public challenge is fulfilled (i.e. accepted by someone)"


class PublicChallengesCancelledByServer(OutgoingEvent[IdList, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all public challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )


class NewActiveGame(OutgoingEvent[GameStartedBroadcastedData, GameListEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Started (for game lists watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new game starts"

    @classmethod
    def payload_examples(cls) -> list[GameStartedBroadcastedData]:
        return game_started_data_samples()


class NewRecentGame(OutgoingEvent[GameEndedBroadcastedData, GameListEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Ended (for game lists watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a game ends"

    @classmethod
    def payload_examples(cls) -> list[GameEndedBroadcastedData]:
        return game_ended_data_samples()


class IncomingChallengeReceived(OutgoingEvent[ChallengePublic, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a direct challenge arrives"

    @classmethod
    def payload_examples(cls) -> list[ChallengePublic]:
        return incoming_challenges()


class IncomingChallengeCancelled(OutgoingEvent[Id, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an incoming direct challenge is cancelled"


class IncomingChallengesCancelledByServer(OutgoingEvent[IdList, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all incoming challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )


class OutgoingChallengeAccepted(OutgoingEvent[Id, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an outgoing (direct or open) challenge is accepted"


class OutgoingChallengeRejected(OutgoingEvent[Id, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an outgoing direct challenge is rejected"


class OutgoingChallengesCancelledByServer(OutgoingEvent[IdList, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all outgoing challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )


class NewPly(OutgoingEvent[PlyBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new move happens on the board"

    @classmethod
    def payload_examples(cls) -> list[PlyBroadcastedData]:
        return [
            ply_broadcasted_data()
            for _ in range(3)
        ]


class NewChatMessage(OutgoingEvent[ChatMessageBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new chat message arrives"

    @classmethod
    def payload_examples(cls) -> list[ChatMessageBroadcastedData]:
        return [
            chat_message_broadcasted_data(False),
            chat_message_broadcasted_data(True),
            chat_message_broadcasted_data(None),
        ]


class OfferActionPerformed(OutgoingEvent[OfferActionBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a draw or takeback offer is created, cancelled, accepted or rejected"

    @classmethod
    def payload_examples(cls) -> list[OfferActionBroadcastedData]:
        return [
            offer_action_broadcasted_data()
            for _ in range(3)
        ]


class TimeAdded(OutgoingEvent[TimeAddedBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a player decides to add time to the opponent's reserves"

    @classmethod
    def payload_examples(cls) -> list[TimeAddedBroadcastedData]:
        return [
            time_added_broadcasted_data()
            for _ in range(3)
        ]


class Rollback(OutgoingEvent[RollbackBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever some of the last moves get cancelled"

    @classmethod
    def payload_examples(cls) -> list[RollbackBroadcastedData]:
        return [
            rollback_broadcasted_data()
            for _ in range(3)
        ]


class GameEnded(OutgoingEvent[GameEndedBroadcastedData, GameEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Ended (for specific game watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted when the game ends"

    @classmethod
    def payload_examples(cls) -> list[GameEndedBroadcastedData]:
        return game_ended_data_samples()


class NewSubscriber(OutgoingEvent[UserRefWithNickname | None, SubscriberListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever a new user subscribes to a respective channel. "
            "Payload will be null for unauthenticated users, otherwise will contain subscriber's reference and nickname"
        )

    @classmethod
    def payload_examples(cls) -> list[UserRefWithNickname | None]:
        return [user_ref_with_nickname() if i != 1 else None for i in range(3)]


class SubscriberLeft(OutgoingEvent[UserRefWithNickname | None, SubscriberListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever a new user unsubscribes from a respective channel. "
            "Payload will be null for unauthenticated users, otherwise will contain subscriber's reference and nickname"
        )

    @classmethod
    def payload_examples(cls) -> list[UserRefWithNickname | None]:
        return [user_ref_with_nickname() if i != 1 else None for i in range(3)]
