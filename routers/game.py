from typing import Sequence
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, desc, select
from models.game import Game, GameFilter, GamePublic
from routers.shared_methods.game import check_timeout
from routers.utils import MutableStateDependency, SessionDependency


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
async def check_timeout_route(*, session: SessionDependency, state: MutableStateDependency, game_id: int):
    await check_timeout(session=session, state=state, game_id=game_id)
