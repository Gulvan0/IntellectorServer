from fastapi import APIRouter, HTTPException, Query

from src.common.dependencies import MutableStateDependency, SecretConfigDependency, SessionDependency
from src.game.methods.cast import to_public_game
from src.game.methods.get import get_current_games, get_recent_games
from src.game.methods.update import check_timeout
from src.game.models.main import Game, GamePublic
from src.game.models.rest import GameFilter
from src.net.base_router import LoggingRoute


router = APIRouter(prefix="/game", route_class=LoggingRoute)


@router.get("/current", response_model=list[GamePublic])
async def get_current_games_route(
    *,
    session: SessionDependency,
    offset: int = 0,
    limit: int = Query(default=10, le=50),
    game_filter: GameFilter = GameFilter()
):
    return [
        await to_public_game(session, game)
        for game in await get_current_games(session, game_filter, offset, limit)
    ]


@router.get("/recent", response_model=list[GamePublic])
async def get_recent_games_route(
    *,
    session: SessionDependency,
    offset: int = 0,
    limit: int = Query(default=10, le=50),
    game_filter: GameFilter = GameFilter()
):
    return [
        await to_public_game(session, game)
        for game in await get_recent_games(session, game_filter, offset, limit)
    ]


@router.get("/{game_id}", response_model=GamePublic)
async def get_game(
    *,
    session: SessionDependency,
    game_id: int
):
    db_game = await session.get(Game, game_id)

    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    return await to_public_game(session, db_game)


@router.get("/{game_id}/check_timeout")
async def check_timeout_route(
    *,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency,
    game_id: int
):
    await check_timeout(session=session, state=state, secret_config=secret_config, game_id=game_id)
