from typing import Annotated
from fastapi import Depends, HTTPException

from src.common.field_types import PlayerLogin
from src.player.models import Player
from src.common.dependencies import SessionDependency


async def get_db_player(session: SessionDependency, login: PlayerLogin) -> Player:
    db_player = await session.get(Player, login)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


DBPlayerDependency = Annotated[Player, Depends(get_db_player)]
