from game.methods.create import create_internal_game
from challenge.methods.get import get_mergeable_challenge
from challenge.models import ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse
from common.user_ref import UserReference
from config.models import SecretConfig
from net.state import MutableState
from utils.async_orm_session import AsyncSession


async def try_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: AsyncSession,
    state: MutableState,
    secret_config: SecretConfig
) -> ChallengeCreateResponse | None:
    mergeable_challenge = await get_mergeable_challenge(session, caller, challenge)
    if not mergeable_challenge:
        return None

    game = await create_internal_game(mergeable_challenge, caller, session, state, secret_config)
    return ChallengeCreateResponse(result="MERGED", game=game)
