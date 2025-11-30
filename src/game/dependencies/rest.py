from typing import Annotated
from fastapi import Depends, HTTPException

from src.common.dependencies import MandatoryUserDependency, SessionDependency
from src.common.user_ref import UserReference
from src.game.models.main import Game
from src.game.models.polymorphous import PayloadWithGameId


async def get_game(session: SessionDependency, payload: PayloadWithGameId) -> Game:
    db_game = await session.get(Game, payload.game_id)
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")
    return db_game


GAME_EXISTS_DEPENDENCY = Depends(get_game)


GameDependency = Annotated[Game, GAME_EXISTS_DEPENDENCY]


async def client_is_uploader(db_game: GameDependency, client: MandatoryUserDependency) -> None:
    if db_game.external_uploader_ref != client.reference:
        if db_game.external_uploader_ref:
            pretty_uploader_ref = UserReference(db_game.external_uploader_ref).pretty()
            message = f"Only {pretty_uploader_ref} can modify this game"
        else:
            message = "Cannot modify internal game"
        raise HTTPException(status_code=403, detail=message)


CLIENT_IS_UPLOADER_DEPENDENCY = Depends(client_is_uploader)


async def game_is_ongoing(db_game: GameDependency) -> None:
    if db_game.outcome:
        raise HTTPException(status_code=400, detail="Game has already ended")


GAME_IS_ONGOING_DEPENDENCY = Depends(game_is_ongoing)
