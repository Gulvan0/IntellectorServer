from src.challenge.models import Challenge, ChallengeFischerTimeControlPublic, ChallengePublic

import src.game.methods.cast as game_cast_methods
import src.player.methods as player_methods
from src.utils.async_orm_session import AsyncSession


async def to_public_challenge(session: AsyncSession, db_challenge: Challenge) -> ChallengePublic:
    resulting_game = None
    if db_challenge.resulting_game:
        resulting_game = await game_cast_methods.to_public_game(session, db_challenge.resulting_game)

    return ChallengePublic(
        acceptor_color=db_challenge.acceptor_color,
        custom_starting_sip=db_challenge.custom_starting_sip,
        rated=db_challenge.rated,
        id=db_challenge.id,
        created_at=db_challenge.created_at,
        caller=player_methods.get_user_ref_with_nickname(session, db_challenge.caller_ref),
        callee=player_methods.get_optional_user_ref_with_nickname(session, db_challenge.callee_ref),
        kind=db_challenge.kind,
        time_control_kind=db_challenge.time_control_kind,
        active=db_challenge.active,
        fischer_time_control=ChallengeFischerTimeControlPublic.cast(db_challenge.fischer_time_control),
        resulting_game=resulting_game
    )
