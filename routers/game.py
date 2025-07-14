from datetime import UTC, timedelta, datetime
import time
from typing import Sequence
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, desc, select
from models.game import Game, GameFilter, GameOutcome, GamePlyEvent, GamePublic
from routers.shared_methods.game import end_game
from routers.utils import MutableStateDependency, SessionDependency
from rules import PieceColor
from utils.datatypes import OutcomeKind


router = APIRouter(prefix="/game")


@router.get("/{game_id}", response_model=GamePublic)
async def get_game(*, session: SessionDependency, game_id: int):
    db_game = session.get(Game, game_id)

    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    return db_game


async def get_current_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome == None,  # noqa
        *game_filter.construct_conditions()
    ).offset(offset).limit(limit)).all()


@router.get("/current", response_model=list[GamePublic])
async def get_current_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_current_games(session, game_filter, offset, limit)


async def get_recent_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(desc(Game.started_at)).offset(offset).limit(limit)).all()


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_recent_games(session, game_filter, offset, limit)


@router.get("/{game_id}/check_timeout")
async def check_timeout(*, session: SessionDependency, state: MutableStateDependency, game_id: int):
    threshold = state.game_timeout_not_earlier_than.get(game_id)
    if not threshold or threshold > time.time():
        return

    if session.get(GameOutcome, game_id):
        return

    last_ply_event = session.exec(select(
        GamePlyEvent
    ).where(
        GamePlyEvent.game_id == game_id
    ).order_by(
        desc(GamePlyEvent.ply_index)
    )).first()

    if not last_ply_event or last_ply_event.ply_index < 1 or not last_ply_event.white_seconds_after_execution or not last_ply_event.black_seconds_after_execution:
        return

    if last_ply_event.ply_index % 2 == 0:
        time_remainder = last_ply_event.black_seconds_after_execution
        potential_winner = PieceColor.WHITE
    else:
        time_remainder = last_ply_event.white_seconds_after_execution
        potential_winner = PieceColor.BLACK

    timeout_dt = (last_ply_event.occurred_at + timedelta(seconds=time_remainder)).replace(tzinfo=UTC)
    if datetime.now(UTC) >= timeout_dt:
        await end_game(session, state, game_id, OutcomeKind.TIMEOUT, potential_winner, timeout_dt)
