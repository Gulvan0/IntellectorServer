from typing import Sequence
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, desc, select
from models.game import Game, GameFilter, GamePublic
from routers.utils import get_session


router = APIRouter(prefix="/game")


@router.get("/{id}", response_model=GamePublic)
async def get_game(*, session: Session = Depends(get_session), id: int):
    db_game = session.get(Game, id)

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
async def get_current_games_route(*, session: Session = Depends(get_session), offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_current_games(session, game_filter, offset, limit)


async def get_recent_games(session: Session, game_filter: GameFilter, offset: int = 0, limit: int = 10) -> Sequence[Game]:
    return session.exec(select(
        Game
    ).where(
        Game.outcome != None,  # noqa
        *game_filter.construct_conditions()
    ).order_by(desc(Game.started_at)).offset(offset).limit(limit)).all()


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(*, session: Session = Depends(get_session), offset: int = 0, limit: int = Query(default=10, le=50), game_filter: GameFilter = GameFilter()):
    return get_recent_games(session, game_filter, offset, limit)
