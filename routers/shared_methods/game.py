from datetime import UTC, datetime, timedelta
import random
import time
from typing import Literal
from sqlalchemy import ScalarResult
from sqlmodel import Session, col, desc, select, func
from models.challenge import Challenge
from models.channel import GameListEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel, StartedPlayerGamesEventChannel
from models.config import SecretConfig
from models.game import (
    Game,
    GameChatMessageEventPublic,
    GameFischerTimeControl,
    GameOfferEvent,
    GameOfferEventPublic,
    GameOutcome,
    GameOutcomePublic,
    GamePlyEvent,
    GamePlyEventPublic,
    GamePublic,
    GameRollbackEventPublic,
    GameStartedBroadcastedData,
    GameStateRefresh,
    GameTimeAddedEventPublic,
)
from models.other import Id
from net.fastapi_wrapper import MutableState
from net.outgoing import WebsocketOutgoingEventRegistry
from routers.shared_methods.notification import delete_new_public_challenge_notifications, delete_game_started_notifications, send_game_started_notifications
from routers.shared_queries.game import get_last_ply_event, get_ongoing_finite_game
from rules import PieceColor, Position
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, FischerTimeControlEntity, OfferAction, OfferKind, OutcomeKind, TimeControlKind, UserReference
from utils.query import count_if


def _assign_player_colors(acceptor_color: ChallengeAcceptorColor, caller_ref: str, acceptor_ref: str) -> tuple[str, str]:
    match acceptor_color:
        case ChallengeAcceptorColor.RANDOM:
            return random.choice([
                (caller_ref, acceptor_ref),
                (acceptor_ref, caller_ref)
            ])
        case ChallengeAcceptorColor.WHITE:
            return acceptor_ref, caller_ref
        case ChallengeAcceptorColor.BLACK:
            return caller_ref, acceptor_ref


async def _create_game(
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    rated: bool,
    custom_starting_sip: str | None,
    external_uploader_ref: str | None,
    session: Session,
    state: MutableState
) -> tuple[Game, GamePublic]:
    db_game = Game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control_kind=TimeControlKind.of(time_control),
        rated=rated,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=external_uploader_ref,
        fischer_time_control=GameFischerTimeControl(
            start_seconds=time_control.start_seconds,
            increment_seconds=time_control.increment_seconds
        ) if time_control else None
    )
    session.add(db_game)
    session.commit()

    public_game = GamePublic.model_construct(**db_game.model_dump())

    for player_ref in [white_player_ref, black_player_ref]:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.GAME_STARTED,
            public_game,
            StartedPlayerGamesEventChannel(watched_ref=player_ref)
        )
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.NEW_ACTIVE_GAME,
        GameStartedBroadcastedData.model_construct(**public_game.model_dump()),
        GameListEventChannel()
    )

    return db_game, public_game


async def create_internal_game(challenge: Challenge, acceptor: UserReference, session: Session, state: MutableState, secret_config: SecretConfig) -> GamePublic:
    white_player_ref, black_player_ref = _assign_player_colors(challenge.acceptor_color, challenge.caller_ref, acceptor.reference)

    db_game, public_game = await _create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=challenge.fischer_time_control,
        rated=challenge.rated,
        custom_starting_sip=challenge.custom_starting_sip,
        external_uploader_ref=None,
        session=session,
        state=state
    )

    challenge.active = False
    challenge.resulting_game = db_game
    session.add(challenge)
    session.commit()

    assert challenge.id

    delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    challenge_id = Id(id=challenge.id)

    if challenge.kind == ChallengeKind.PUBLIC:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.PUBLIC_CHALLENGE_FULFILLED,
            challenge_id,
            PublicChallengeListEventChannel()
        )

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_ACCEPTED,
        challenge_id,
        OutgoingChallengesEventChannel(user_ref=challenge.caller_ref)
    )

    send_game_started_notifications(white_player_ref, black_player_ref, public_game, secret_config.integrations, session)

    return public_game


async def create_external_game(
    uploader: UserReference,
    white_player_ref: str,
    black_player_ref: str,
    time_control: FischerTimeControlEntity | None,
    custom_starting_sip: str | None,
    session: Session,
    state: MutableState
) -> GamePublic:
    _, public_game = await _create_game(
        white_player_ref=white_player_ref,
        black_player_ref=black_player_ref,
        time_control=time_control,
        rated=False,
        custom_starting_sip=custom_starting_sip,
        external_uploader_ref=uploader.reference,
        session=session,
        state=state
    )

    return public_game


def get_ply_history(session: Session, game_id: int, reverse_order: bool = False) -> ScalarResult[GamePlyEvent]:
    return session.exec(select(
        GamePlyEvent
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    ).order_by(
        desc(GamePlyEvent.ply_index) if reverse_order else col(GamePlyEvent.ply_index)
    ))


def get_ply_cnt(session: Session, game_id: int) -> int:
    last_ply_index = session.exec(select(
        func.max(GamePlyEvent.ply_index)
    ).where(
        GamePlyEvent.game_id == game_id,
        not GamePlyEvent.is_cancelled
    )).first()
    return last_ply_index + 1 if last_ply_index else 0


def compose_state_refresh(
    session: Session,
    game_id: int,
    game: Game,
    reason: Literal['sub', 'invalid_move'],
    include_spectator_messages: bool
) -> GameStateRefresh:
    return GameStateRefresh(
        game_id=game_id,
        refresh_reason=reason,
        outcome=GameOutcomePublic.model_construct(**game.outcome.model_dump()) if game.outcome else None,
        ply_events=[GamePlyEventPublic.model_construct(**event.model_dump()) for event in get_ply_history(session, game_id)],
        chat_message_events=[
            GameChatMessageEventPublic.model_construct(**event.model_dump())
            for event in game.chat_message_events
            if include_spectator_messages or not event.spectator
        ],
        offer_events=[GameOfferEventPublic.model_construct(**event.model_dump()) for event in game.offer_events],
        time_added_events=[GameTimeAddedEventPublic.model_construct(**event.model_dump()) for event in game.time_added_events],
        rollback_events=[GameRollbackEventPublic.model_construct(**event.model_dump()) for event in game.rollback_events],
    )


def get_active_offers(session: Session, game_id: int) -> ScalarResult[GameOfferEvent]:
    return session.exec(
        select(
            GameOfferEvent
        ).where(
            GameOfferEvent.game_id == game_id
        ).group_by(
            GameOfferEvent.offer_kind,
            GameOfferEvent.offer_author
        ).having(
            count_if(GameOfferEvent.action == OfferAction.CREATE) > count_if(GameOfferEvent.action != OfferAction.CREATE)
        )
    )


def is_offer_active(session: Session, game_id: int, offer_kind: OfferKind, offer_author: PieceColor) -> bool:
    return session.exec(
        select(
            GameOfferEvent.action
        ).where(
            GameOfferEvent.game_id == game_id,
            GameOfferEvent.offer_kind == offer_kind,
            GameOfferEvent.offer_author == offer_author
        ).order_by(
            desc(GameOfferEvent.occurred_at)
        )
    ).first() == OfferAction.CREATE.value


async def end_game(
    session: Session,
    state: MutableState,
    secret_config: SecretConfig,
    game_id: int,
    outcome: OutcomeKind,
    winner_color: PieceColor | None,
    ended_at: datetime | None = None
) -> None:  # TODO: Add precalculated args: time reserves, last ply, ...
    # TODO: Add to outcome table, ensure time reserves equality compared to ply table
    # TODO: Send game ended events (multiple channels)

    delete_game_started_notifications(
        game_id=game_id,
        vk_token=secret_config.integrations.vk.token,
        session=session
    )

    if state.shutdown_activated and not get_ongoing_finite_game(session):
        raise KeyboardInterrupt

    state.game_timeout_not_earlier_than.pop(game_id, None)


async def check_timeout(
    *,
    session: Session,
    state: MutableState,
    secret_config: SecretConfig,
    game_id: int,
    last_ply_event: GamePlyEvent | None | Literal['NOT_YET_RETRIEVED'] = 'NOT_YET_RETRIEVED',
    last_position: Position | Literal['NOT_YET_RETRIEVED'] = 'NOT_YET_RETRIEVED',
    outcome_abscence_checked: bool = False,
) -> bool:
    threshold = state.game_timeout_not_earlier_than.get(game_id)
    if not threshold or threshold > time.time():
        return False

    if not outcome_abscence_checked and session.get(GameOutcome, game_id) is not None:
        return False

    if last_ply_event == 'NOT_YET_RETRIEVED':
        last_ply_event = get_last_ply_event(session, game_id)

    if not last_ply_event or last_ply_event.ply_index < 1 or not last_ply_event.white_ms_after_execution or not last_ply_event.black_ms_after_execution:
        return False

    if last_position == 'NOT_YET_RETRIEVED':
        last_position = Position.from_sip(last_ply_event.sip_after)

    if last_position.color_to_move == PieceColor.BLACK:  # we don't use ply_index as the starting position might have been "black to move"
        time_remainder = last_ply_event.black_ms_after_execution
        potential_winner = PieceColor.WHITE
    else:
        time_remainder = last_ply_event.white_ms_after_execution
        potential_winner = PieceColor.BLACK

    timeout_dt = (last_ply_event.occurred_at + timedelta(milliseconds=time_remainder)).replace(tzinfo=UTC)
    if datetime.now(UTC) >= timeout_dt:
        await end_game(session, state, secret_config, game_id, OutcomeKind.TIMEOUT, potential_winner, timeout_dt)
        return True

    return False
