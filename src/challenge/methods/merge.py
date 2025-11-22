from src.net.utils.early_response import EarlyResponse
from src.challenge.methods.get import get_mergeable_challenge
from src.challenge.models import ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse
from src.common.user_ref import UserReference
from src.config.models import SecretConfig
from src.net.core import MutableState

import src.game.methods.create as game_create_methods
from src.utils.async_orm_session import AsyncSession


async def try_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: AsyncSession,
    state: MutableState,
    secret_config: SecretConfig
) -> None:
    mergeable_challenge = await get_mergeable_challenge(session, caller, challenge)
    if mergeable_challenge:
        game = await game_create_methods.create_internal_game(mergeable_challenge, caller, session, state, secret_config)
        response = ChallengeCreateResponse(result="merged", game=game)
        raise EarlyResponse(status_code=200, body=response)
