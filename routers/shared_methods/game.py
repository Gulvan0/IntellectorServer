from datetime import UTC, datetime, timedelta
import time
from typing import Literal
from sqlalchemy import ScalarResult
from sqlmodel import Session, col, desc, select, func
from models.game import (
    Game,
    GameChatMessageEventPublic,
    GameOfferEvent,
    GameOfferEventPublic,
    GameOutcome,
    GameOutcomePublic,
    GamePlyEvent,
    GamePlyEventPublic,
    GameRollbackEventPublic,
    GameStateRefresh,
    GameTimeAddedEventPublic,
)
from net.fastapi_wrapper import MutableState
from routers.shared_queries.game import get_last_ply_event, get_ongoing_finite_game
from rules import PieceColor, Position
from utils.datatypes import OfferAction, OfferKind, OutcomeKind
from utils.query import count_if


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
    game_id: int,
    outcome: OutcomeKind,
    winner_color: PieceColor | None,
    ended_at: datetime | None = None
) -> None:  # TODO: Add precalculated args: time reserves, last ply, ...
    # TODO: Add to outcome table, ensure time reserves equality compared to ply table
    # TODO: Send game ended events (multiple channels)
    # TODO: Delete VK chat message

    if state.shutdown_activated and not get_ongoing_finite_game(session):
        raise KeyboardInterrupt

    state.game_timeout_not_earlier_than.pop(game_id, None)


async def check_timeout(
    *,
    session: Session,
    state: MutableState,
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
        await end_game(session, state, game_id, OutcomeKind.TIMEOUT, potential_winner, timeout_dt)
        return True

    return False
