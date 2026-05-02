from enum import Enum, auto
from typing import Annotated
from fastapi import Depends, HTTPException, Request

from board.piece import PieceColor
from common.dependencies import MandatoryUserDependency, SessionDependency
from common.user_ref import UserReference
from game.models.main import Game


class GameLoadOptions(Enum):
    NONE = auto()
    JUST_OUTCOME = auto()
    SUMMARY = auto()
    FULL = auto()


async def __get_game(session: SessionDependency, request: Request, load_options_kind: GameLoadOptions) -> Game:
    payload = await request.json()
    game_id = payload.get('game_id')
    if game_id is None:
        raise HTTPException(500, 'Game dependencies require payloads with game_id field')

    match load_options_kind:
        case GameLoadOptions.NONE:
            options = None
        case GameLoadOptions.JUST_OUTCOME:
            options = Game.load_options(just_summary=True, include_time_control=False)
        case GameLoadOptions.SUMMARY:
            options = Game.load_options(just_summary=True)
        case GameLoadOptions.FULL:
            options = Game.load_options(just_summary=False)

    db_game = await session.get(Game, game_id, options=options)
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")
    return db_game


async def get_game(session: SessionDependency, request: Request) -> Game:
    return await __get_game(session, request, GameLoadOptions.NONE)


GAME_EXISTS_DEPENDENCY = Depends(get_game)


GameDependency = Annotated[Game, GAME_EXISTS_DEPENDENCY]


async def get_game_with_outcome(session: SessionDependency, request: Request) -> Game:
    return await __get_game(session, request, GameLoadOptions.JUST_OUTCOME)


GameWithOutcomeDependency = Annotated[Game, Depends(get_game_with_outcome)]


async def get_summarized_game(session: SessionDependency, request: Request) -> Game:
    return await __get_game(session, request, GameLoadOptions.SUMMARY)


SummarizedGameDependency = Annotated[Game, Depends(get_summarized_game)]


async def get_full_game(session: SessionDependency, request: Request) -> Game:
    return await __get_game(session, request, GameLoadOptions.FULL)


FullGameDependency = Annotated[Game, Depends(get_full_game)]


async def client_is_uploader(db_game: GameDependency, client: MandatoryUserDependency) -> None:
    if db_game.external_uploader_ref != client.reference:
        if db_game.external_uploader_ref:
            pretty_uploader_ref = UserReference(db_game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = f"Game {db_game.id} is internal; use /game/internal/... API routes to interact with it"
        raise HTTPException(status_code=403, detail=message)


CLIENT_IS_UPLOADER_DEPENDENCY = Depends(client_is_uploader)


async def internal_or_client_is_uploader(db_game: GameDependency, client: MandatoryUserDependency) -> None:
    if db_game.external_uploader_ref and db_game.external_uploader_ref != client.reference:
        pretty_uploader_ref = UserReference(db_game.external_uploader_ref).pretty()
        raise HTTPException(status_code=403, detail=f"Only {pretty_uploader_ref} can modify this game")


CLIENT_IS_UPLOADER_IF_EXTERNAL_DEPENDENCY = Depends(internal_or_client_is_uploader)


async def game_is_ongoing(db_game: GameDependency) -> None:
    if db_game.outcome:
        raise HTTPException(status_code=403, detail="Game has already ended")


GAME_IS_ONGOING_DEPENDENCY = Depends(game_is_ongoing)


async def get_player_color(db_game: GameDependency, client: MandatoryUserDependency) -> PieceColor | None:
    if client.reference == db_game.white_player_ref:
        return PieceColor.WHITE
    elif client.reference == db_game.black_player_ref:
        return PieceColor.BLACK
    return None


OptionalPlayerColorDependency = Annotated[PieceColor | None, Depends(get_player_color)]


async def get_mandatory_player_color(db_game: GameDependency, client: MandatoryUserDependency) -> PieceColor:
    color = await get_player_color(db_game, client)
    if color:
        return color
    raise HTTPException(status_code=403, detail=f"You are not a player in game {db_game.id}")


CLIENT_IS_PARTICIPANT_DEPENDENCY = Depends(get_mandatory_player_color)


PlayerColorDependency = Annotated[PieceColor, CLIENT_IS_PARTICIPANT_DEPENDENCY]


async def game_is_internal(db_game: GameDependency) -> None:
    if db_game.external_uploader_ref:
        raise HTTPException(status_code=409, detail=f"Game {db_game.id} is external; use /game/external/... API routes to interact with it")


GAME_IS_INTERNAL_DEPENDENCY = Depends(game_is_internal)
