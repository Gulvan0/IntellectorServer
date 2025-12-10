from datetime import UTC, datetime

from src.common.time_control import TimeControlKind
from src.game.datatypes import OfferAction, OfferKind, OutcomeKind
from src.game.models.chat import GameChatMessageEventPublic
from src.game.models.main import GamePublic
from src.game.models.offer import GameOfferEventPublic
from src.game.models.outcome import GameOutcomePublic
from src.game.models.ply import GamePlyEventPublic
from src.game.models.rollback import GameRollbackEventPublic
from src.game.models.time_added import GameTimeAddedEventPublic
from src.game.models.time_control import GameFischerTimeControlPublic
from src.game.models.time_update import GameTimeUpdatePublic, GameTimeUpdateReason
from src.pubsub.models.channel import EveryoneEventChannel, StartedPlayerGamesEventChannel
from src.pubsub.outgoing_event.base import OutgoingEvent
from src.rules import PieceColor, PieceKind


# TODO: Make foreign imports absolute


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
            white_player_ref="some_player",
            black_player_ref="other_player",
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
                    author_ref="some_player",
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

# TODO: Add the remaining ones + two new ones ("new subscriber", "subscriber left")
