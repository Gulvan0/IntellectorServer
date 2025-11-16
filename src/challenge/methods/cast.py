from sqlmodel import Session
from src.challenge.models import Challenge, ChallengePublic

import src.game.methods.cast as game_cast_methods


def to_public_challenge(session: Session, db_challenge: Challenge) -> ChallengePublic:
    resulting_game = None
    if db_challenge.resulting_game:
        resulting_game = game_cast_methods.to_public_game(session, db_challenge.resulting_game)

    return db_challenge.to_public(resulting_game)
