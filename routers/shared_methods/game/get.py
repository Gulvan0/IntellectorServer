from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy import ScalarResult
from sqlmodel import Session, col, desc, select, func
from models.game import (
    GameOfferEvent,
    GamePlyEvent,
)
from models.game.time_update import GameTimeUpdate, GameTimeUpdateReason
from routers.shared_queries.game import get_latest_time_update
from rules import PieceColor
from utils.datatypes import OfferAction, OfferKind
from utils.query import count_if


@dataclass
class TimeoutReachedException(Exception):
    winner: PieceColor
    reached_at: datetime


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


def construct_new_ply_time_update(
    session: Session,
    game_id: int,
    ply_dt: datetime,
    new_ply_index: int,
    color_to_move: PieceColor,
    timeout_grace_ms: int
) -> GameTimeUpdate | None:
    latest_time_update = get_latest_time_update(session, game_id)
    if not latest_time_update:
        return None

    new_time_update = latest_time_update.model_copy()
    new_time_update.reason = GameTimeUpdateReason.PLY
    new_time_update.updated_at = ply_dt

    if latest_time_update.ticking_side:
        ms_passed = int((ply_dt - latest_time_update.updated_at).total_seconds() * 1000)
        if latest_time_update.ticking_side == PieceColor.WHITE:
            new_time_update.white_ms -= ms_passed
            remaining_time = new_time_update.white_ms
        else:
            new_time_update.black_ms -= ms_passed
            remaining_time = new_time_update.black_ms

        if remaining_time <= -timeout_grace_ms:
            timed_out_at = ply_dt + timedelta(milliseconds=remaining_time)
            raise TimeoutReachedException(winner=latest_time_update.ticking_side.opposite(), reached_at=timed_out_at)

    new_time_update.ticking_side = color_to_move if new_ply_index >= 1 else None

    return new_time_update
