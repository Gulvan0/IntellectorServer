from datetime import UTC, datetime

from src.challenge.datatypes import ChallengeKind
from src.challenge.models import ChallengeFischerTimeControlPublic, ChallengePublic
from src.common.models import Id, IdList, UserRefWithNickname
from src.common.time_control import TimeControlKind
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind
from src.game.models.chat import ChatMessageBroadcastedData, GameChatMessageEventPublic
from src.game.models.main import GamePublic, GameStartedBroadcastedData
from src.game.models.offer import GameOfferEventPublic, OfferActionBroadcastedData
from src.game.models.outcome import GameEndedBroadcastedData, GameOutcomePublic
from src.game.models.ply import GamePlyEventPublic, PlyBroadcastedData
from src.game.models.rollback import GameRollbackEventPublic, RollbackBroadcastedData
from src.game.models.time_added import GameTimeAddedEventPublic, TimeAddedBroadcastedData
from src.game.models.time_control import GameFischerTimeControlPublic
from src.game.models.time_update import GameTimeUpdatePublic, GameTimeUpdateReason
from src.pubsub.models.channel import (
    EveryoneEventChannel,
    GameEventChannel,
    GameListEventChannel,
    IncomingChallengesEventChannel,
    OutgoingChallengesEventChannel,
    PublicChallengeListEventChannel,
    StartedPlayerGamesEventChannel,
    SubscriberListEventChannel,
)
from src.pubsub.outgoing_event.base import OutgoingEvent
from src.rules import PieceColor, PieceKind


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
    def payload_example(cls) -> GamePublic:
        # TODO: Move all sample models to a separate module (or to their definitions)
        return GamePublic(
            white_player=UserRefWithNickname(
                user_ref="some_login",
                nickname="Some Nickname"
            ),
            black_player=UserRefWithNickname(
                user_ref="other_login",
                nickname="Other Nickname"
            ),
            time_control_kind=TimeControlKind.BLITZ,
            rated=False,
            custom_starting_sip="2!wqgtrurvrwrxryi1i2o4n5g6o!AoCnEoFiGeHeJrKrLrMrNrQi",  # TODO: Replace with dynamically calculated
            external_uploader_ref="uploader_login",
            id=1337,
            fischer_time_control=GameFischerTimeControlPublic(
                start_seconds=180,
                increment_seconds=2
            ),
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
            events=[
                GamePlyEventPublic(
                    ply_index=0,
                    from_i=1,
                    from_j=4,
                    to_i=3,
                    to_j=3,
                    morph_into=PieceKind.DEFENSOR,
                    time_update=GameTimeUpdatePublic(
                        updated_at=datetime.now(UTC),
                        white_ms=180000,
                        black_ms=180000,
                        ticking_side=None,
                        reason=GameTimeUpdateReason.PLY
                    )
                ),
                GameChatMessageEventPublic(
                    author=UserRefWithNickname(
                        user_ref="some_login",
                        nickname="Some Nickname"
                    ),
                    text="Все, я победил!",
                    spectator=False
                ),
                GameOfferEventPublic(
                    action=OfferAction.CREATE,
                    offer_kind=OfferKind.TAKEBACK,
                    offer_author=PieceColor.WHITE
                ),
                GameTimeAddedEventPublic(
                    amount_seconds=15,
                    receiver=PieceColor.BLACK,
                    time_update=GameTimeUpdatePublic(
                        updated_at=datetime.now(UTC),
                        white_ms=180000,
                        black_ms=195000,
                        ticking_side=None,
                        reason=GameTimeUpdateReason.TIME_ADDED
                    )
                ),
                GameOfferEventPublic(
                    action=OfferAction.ACCEPT,
                    offer_kind=OfferKind.TAKEBACK,
                    offer_author=PieceColor.WHITE
                ),
                GameRollbackEventPublic(
                    ply_cnt_before=1,
                    ply_cnt_after=0,
                    requested_by=PieceColor.WHITE,
                    time_update=GameTimeUpdatePublic(
                        updated_at=datetime.now(UTC),
                        white_ms=180000,
                        black_ms=180000,
                        ticking_side=None,
                        reason=GameTimeUpdateReason.ROLLBACK
                    )
                ),
            ],
            latest_time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.GAME_ENDED
            )
        )


class NewPublicChallenge(OutgoingEvent[ChallengePublic, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new public challenge is created"

    @classmethod
    def payload_example(cls) -> ChallengePublic:
        return ChallengePublic(
            rated=True,
            id=123,
            created_at=datetime.now(UTC),
            caller=UserRefWithNickname(
                user_ref="some_login",
                nickname="Some Nickname"
            ),
            callee=None,
            kind=ChallengeKind.DIRECT,
            time_control_kind=TimeControlKind.BLITZ,
            active=False,
            fischer_time_control=ChallengeFischerTimeControlPublic(
                start_seconds=180,
                increment_seconds=2
            ),
            resulting_game=None
        )


class PublicChallengeCancelled(OutgoingEvent[Id, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a public challenge is cancelled"

    @classmethod
    def payload_example(cls) -> Id:
        return Id(id=123)


class PublicChallengeFulfilled(OutgoingEvent[Id, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a public challenge is fulfilled (i.e. accepted by someone)"

    @classmethod
    def payload_example(cls) -> Id:
        return Id(id=123)


class PublicChallengesCancelledByServer(OutgoingEvent[IdList, PublicChallengeListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all public challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )

    @classmethod
    def payload_example(cls) -> IdList:
        return IdList(ids=[123, 125])


class NewActiveGame(OutgoingEvent[GameStartedBroadcastedData, GameListEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Started (for game lists watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new game starts"

    @classmethod
    def payload_example(cls) -> GameStartedBroadcastedData:
        return GameStartedBroadcastedData(
            white_player=UserRefWithNickname(
                user_ref="some_login",
                nickname="Some Nickname"
            ),
            black_player=UserRefWithNickname(
                user_ref="other_login",
                nickname="Other Nickname"
            ),
            time_control_kind=TimeControlKind.BLITZ,
            rated=True,
            custom_starting_sip="2!wqgtrurvrwrxryi1i2o4n5g6o!AoCnEoFiGeHeJrKrLrMrNrQi",
            external_uploader_ref="external_uploader_login",
            id=123,
            fischer_time_control=GameFischerTimeControlPublic(
                start_seconds=180,
                increment_seconds=2
            ),
        )


class NewRecentGame(OutgoingEvent[GameEndedBroadcastedData, GameListEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Ended (for game lists watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a game ends"

    @classmethod
    def payload_example(cls) -> GameEndedBroadcastedData:
        return GameEndedBroadcastedData(
            kind=OutcomeKind.BREAKTHROUGH,
            winner=PieceColor.BLACK,
            game_id=123,
            time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.GAME_ENDED
            )
        )


class IncomingChallengeReceived(OutgoingEvent[ChallengePublic, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a direct challenge arrives"

    @classmethod
    def payload_example(cls) -> ChallengePublic:
        return ChallengePublic(
            rated=True,
            id=123,
            created_at=datetime.now(UTC),
            caller=UserRefWithNickname(
                user_ref="some_login",
                nickname="Some Nickname"
            ),
            callee=UserRefWithNickname(
                user_ref="other_login",
                nickname="Other Nickname"
            ),
            kind=ChallengeKind.DIRECT,
            time_control_kind=TimeControlKind.BLITZ,
            active=False,
            fischer_time_control=ChallengeFischerTimeControlPublic(
                start_seconds=180,
                increment_seconds=2
            ),
            resulting_game=None
        )


class IncomingChallengeCancelled(OutgoingEvent[Id, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an incoming direct challenge is cancelled"

    @classmethod
    def payload_example(cls) -> Id:
        return Id(id=123)


class IncomingChallengesCancelledByServer(OutgoingEvent[IdList, IncomingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all incoming challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )

    @classmethod
    def payload_example(cls) -> IdList:
        return IdList(ids=[123, 125])


class OutgoingChallengeAccepted(OutgoingEvent[Id, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an outgoing (direct or open) challenge is accepted"

    @classmethod
    def payload_example(cls) -> Id:
        return Id(id=123)


class OutgoingChallengeRejected(OutgoingEvent[Id, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever an outgoing direct challenge is rejected"

    @classmethod
    def payload_example(cls) -> Id:
        return Id(id=123)


class OutgoingChallengesCancelledByServer(OutgoingEvent[IdList, OutgoingChallengesEventChannel]):
    @classmethod
    def description(cls) -> str:
        return (
            "Broadcasted whenever the server cancels all outgoing challenges due to shutdown."
            " The list of the cancelled challenges' IDs is included in the payload just for completeness and transparency."
            " A client may ignore it and interpret this event as 'all challenges are cancelled' and still get the identical results."
            " The server will ALWAYS cancel ALL active challenges"
        )

    @classmethod
    def payload_example(cls) -> IdList:
        return IdList(ids=[123, 125])


class NewPly(OutgoingEvent[PlyBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new move happens on the board"

    @classmethod
    def payload_example(cls) -> PlyBroadcastedData:
        return PlyBroadcastedData(
            ply_index=8,
            from_i=6,
            from_j=3,
            to_i=6,
            to_j=4,
            morph_into=PieceKind.AGGRESSOR,
            game_id=123,
            sip_after="2!wqgtrurvrwrxryi1i2o4n5g6o!AoCnEoFiGeHeJrKrLrMrNrQi",
            time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.PLY
            )
        )


class NewChatMessage(OutgoingEvent[ChatMessageBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new chat message arrives"

    @classmethod
    def payload_example(cls) -> ChatMessageBroadcastedData:
        return ChatMessageBroadcastedData(
            author=UserRefWithNickname(
                user_ref="some_login",
                nickname="Some Nickname"
            ),
            text="Все, я победил!",
            spectator=False,
            game_id=123
        )


class OfferActionPerformed(OutgoingEvent[OfferActionBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a draw or takeback offer is created, cancelled, accepted or rejected"

    @classmethod
    def payload_example(cls) -> OfferActionBroadcastedData:
        return OfferActionBroadcastedData(
            action=OfferAction.ACCEPT,
            offer_kind=OfferKind.TAKEBACK,
            offer_author=PieceColor.WHITE,
            game_id=123
        )


class TimeAdded(OutgoingEvent[TimeAddedBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a player decides to add time to the opponent's reserves"

    @classmethod
    def payload_example(cls) -> TimeAddedBroadcastedData:
        return TimeAddedBroadcastedData(
            game_id=123,
            amount_seconds=15,
            receiver=PieceColor.BLACK,
            time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=195000,
                ticking_side=None,
                reason=GameTimeUpdateReason.TIME_ADDED
            )
        )


class Rollback(OutgoingEvent[RollbackBroadcastedData, GameEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever some of the last moves get cancelled"

    @classmethod
    def payload_example(cls) -> RollbackBroadcastedData:
        return RollbackBroadcastedData(
            game_id=123,
            ply_cnt_before=1,
            ply_cnt_after=0,
            requested_by=PieceColor.WHITE,
            time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.ROLLBACK
            ),
            updated_sip="2!wqgtrurvrwrxryi1i2o4n5g6o!AoCnEoFiGeHeJrKrLrMrNrQi"
        )


class GameEnded(OutgoingEvent[GameEndedBroadcastedData, GameEventChannel]):
    @classmethod
    def title(cls) -> str:
        return "Game Ended (for specific game watchers)"

    @classmethod
    def description(cls) -> str:
        return "Broadcasted when the game ends"

    @classmethod
    def payload_example(cls) -> GameEndedBroadcastedData:
        return GameEndedBroadcastedData(
            game_id=123,
            kind=OutcomeKind.RESIGN,
            winner=PieceColor.BLACK,
            time_update=GameTimeUpdatePublic(
                updated_at=datetime.now(UTC),
                white_ms=180000,
                black_ms=180000,
                ticking_side=None,
                reason=GameTimeUpdateReason.GAME_ENDED
            )
        )


class NewSubscriber(OutgoingEvent[UserRefWithNickname, SubscriberListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new user subscribes to a respective channel"

    @classmethod
    def payload_example(cls) -> UserRefWithNickname:
        return UserRefWithNickname(
            user_ref="some_login",
            nickname="Some Nickname"
        )


class SubscriberLeft(OutgoingEvent[UserRefWithNickname, SubscriberListEventChannel]):
    @classmethod
    def description(cls) -> str:
        return "Broadcasted whenever a new user unsubscribes from a respective channel"

    @classmethod
    def payload_example(cls) -> UserRefWithNickname:
        return UserRefWithNickname(
            user_ref="some_login",
            nickname="Some Nickname"
        )
