from src.challenge.models import Challenge, ChallengePublic

import src.game.methods.cast as game_cast_methods
from src.utils.async_orm_session import AsyncSession


async def to_public_challenge(session: AsyncSession, db_challenge: Challenge) -> ChallengePublic:
    resulting_game = None
    if db_challenge.resulting_game:
        resulting_game = await game_cast_methods.to_public_game(session, db_challenge.resulting_game)

    return db_challenge.to_public(resulting_game)
