from typing import Annotated
from fastapi import Depends, HTTPException

from common.field_types import PlayerLogin
from player.models import Player
from common.dependencies import SessionDependency


async def get_db_player(session: SessionDependency, login: PlayerLogin) -> Player:
    db_player = await session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


PLAYER_EXISTS_DEPENDENCY = Depends(get_db_player)


DBPlayerDependency = Annotated[Player, PLAYER_EXISTS_DEPENDENCY]
