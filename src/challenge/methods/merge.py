from challenge.datatypes import ChallengeAcceptorColor
from game.methods.create import create_internal_game
from challenge.methods.deactivate import deactivate_challenge
from challenge.methods.get import get_mergeable_challenge
from challenge.models import ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse
from common.user_ref import UserReference
from config.models import MainConfig, SecretConfig
from net.state import MutableState
from utils.async_orm_session import AsyncSession


def _merged_acceptor_color(existing: ChallengeAcceptorColor, new: ChallengeAcceptorColor) -> ChallengeAcceptorColor:
    """The new challenge's caller accepts the existing one, so what they asked of their acceptor is what the existing caller gets"""
    if existing != ChallengeAcceptorColor.RANDOM:
        return existing
    match new:
        case ChallengeAcceptorColor.WHITE:
            return ChallengeAcceptorColor.BLACK
        case ChallengeAcceptorColor.BLACK:
            return ChallengeAcceptorColor.WHITE
        case ChallengeAcceptorColor.RANDOM:
            return ChallengeAcceptorColor.RANDOM


async def try_merging(
    challenge: ChallengeCreateOpen | ChallengeCreateDirect,
    caller: UserReference,
    session: AsyncSession,
    state: MutableState,
    main_config: MainConfig,
    secret_config: SecretConfig
) -> ChallengeCreateResponse | None:
    mergeable_challenge = await get_mergeable_challenge(session, caller, challenge)
    if not mergeable_challenge or not mergeable_challenge.id:
        return None

    if not await deactivate_challenge(mergeable_challenge.id, session):
        return None  # taken a moment ago: the new challenge just stands on its own

    acceptor_color = _merged_acceptor_color(mergeable_challenge.acceptor_color, challenge.acceptor_color)
    game = await create_internal_game(mergeable_challenge, caller, session, state, main_config, secret_config, acceptor_color)
    return ChallengeCreateResponse(result="MERGED", game=game)
