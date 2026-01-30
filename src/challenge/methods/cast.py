from challenge.models import Challenge, ChallengeFischerTimeControlPublic, ChallengePublic
from game.methods.cast import to_public_game
from player.methods import get_optional_user_ref_with_nickname, get_user_ref_with_nickname
from utils.async_orm_session import AsyncSession


async def to_public_challenge(session: AsyncSession, db_challenge: Challenge) -> ChallengePublic:
    resulting_game = None
    if db_challenge.resulting_game:
        resulting_game = await to_public_game(session, db_challenge.resulting_game)

    return ChallengePublic(
        acceptor_color=db_challenge.acceptor_color,
        custom_starting_sip=db_challenge.custom_starting_sip,
        rated=db_challenge.rated,
        id=db_challenge.id,
        created_at=db_challenge.created_at,
        caller=get_user_ref_with_nickname(session, db_challenge.caller_ref),
        callee=get_optional_user_ref_with_nickname(session, db_challenge.callee_ref),
        kind=db_challenge.kind,
        time_control_kind=db_challenge.time_control_kind,
        active=db_challenge.active,
        fischer_time_control=ChallengeFischerTimeControlPublic.cast(db_challenge.fischer_time_control),
        resulting_game=resulting_game
    )
