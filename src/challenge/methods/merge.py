from game.methods.create import create_internal_game
from net.utils.early_response import EarlyResponse
from challenge.methods.get import get_mergeable_challenge
from challenge.models import ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse
from common.user_ref import UserReference
from config.models import SecretConfig
from net.core import MutableState
from utils.async_orm_session import AsyncSession


async def try_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: AsyncSession,
    state: MutableState,
    secret_config: SecretConfig
) -> None:
    mergeable_challenge = await get_mergeable_challenge(session, caller, challenge)
    if mergeable_challenge:
        game = await create_internal_game(mergeable_challenge, caller, session, state, secret_config)
        response = ChallengeCreateResponse(result="MERGED", game=game)
        raise EarlyResponse(status_code=200, body=response)
