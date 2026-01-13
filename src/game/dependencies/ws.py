from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from src.common.user_ref import UserReference
from src.game.exceptions import SinkException
from src.game.models.main import Game
from src.net.core import WebSocketWrapper
from src.net.utils.ws_error import WebSocketException
from src.rules.piece import PieceColor
from src.utils.async_orm_session import AsyncSession


@dataclass
class PlayerGameDependencies:
    session: AsyncSession
    db_game: Game
    client_color: PieceColor


@dataclass
class AnyUserGameDependencies:
    session: AsyncSession
    db_game: Game
    client: UserReference


@asynccontextmanager
async def player_dependencies(
    ws: WebSocketWrapper,
    client: UserReference | None,
    game_id: int,
    *,
    ended: bool | None = None
) -> AsyncGenerator[PlayerGameDependencies, None]:
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        db_game = await session.get(Game, game_id)
        if not db_game:
            raise WebSocketException(f"Game {game_id} does not exist")

        if db_game.external_uploader_ref:
            raise WebSocketException(f"Game {game_id} is external; use REST endpoints instead")

        if ended is True and not db_game.outcome:
            raise WebSocketException(f"Game {game_id} is still ongoing")
        if ended is False and db_game.outcome:
            raise WebSocketException(f"Game {game_id} has already ended")

        if client.reference == db_game.white_player_ref:
            client_color = PieceColor.WHITE
        elif client.reference == db_game.black_player_ref:
            client_color = PieceColor.BLACK
        else:
            raise WebSocketException(f"You are not the player in game {game_id}")

        try:
            yield PlayerGameDependencies(session, db_game, client_color)
        except SinkException as e:
            raise WebSocketException(e.message)


@asynccontextmanager
async def any_user_dependencies(
    ws: WebSocketWrapper,
    client: UserReference | None,
    game_id: int,
    *,
    ended: bool | None = None
) -> AsyncGenerator[AnyUserGameDependencies, None]:
    if not client:
        raise WebSocketException("Authorization required. Please provide an auth token")

    async with ws.app.get_db_session() as session:
        db_game = session.get(Game, game_id)
        if not db_game:
            raise WebSocketException(f"Game {game_id} does not exist")

        if db_game.external_uploader_ref:
            raise WebSocketException(f"Game {game_id} is external; use REST endpoints instead")

        if ended is True and not db_game.outcome:
            raise WebSocketException(f"Game {game_id} is still ongoing")
        if ended is False and db_game.outcome:
            raise WebSocketException(f"Game {game_id} has already ended")

        try:
            yield AnyUserGameDependencies(session, db_game, client)
        except SinkException as e:
            raise WebSocketException(e.message)
