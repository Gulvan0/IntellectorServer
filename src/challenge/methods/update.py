from sqlmodel import select
from src.challenge.datatypes import ChallengeKind
from src.challenge.models import Challenge
from src.common.models import Id
from src.config.models import SecretConfig
from src.net.core import MutableState

from src.net.outgoing import WebsocketOutgoingEventRegistry
import src.notification.methods as notification_methods
from src.pubsub.models import IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel
from src.utils.async_orm_session import AsyncSession


async def cancel_challenge(challenge: Challenge, session: AsyncSession, state: MutableState, secret_config: SecretConfig) -> None:
    assert challenge.id

    await notification_methods.delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    challenge.active = False

    if challenge.kind == ChallengeKind.PUBLIC:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.PUBLIC_CHALLENGE_CANCELLED,
            Id(id=challenge.id),
            PublicChallengeListEventChannel()
        )
    elif challenge.kind == ChallengeKind.DIRECT and challenge.callee_ref:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_CANCELLED,
            Id(id=challenge.id),
            IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
        )


async def cancel_all_challenges(session: AsyncSession, state: MutableState, secret_config: SecretConfig):
    challenges = await session.exec(select(Challenge).where(Challenge.active == True))  # noqa
    for challenge in challenges:
        await cancel_challenge(challenge, session, state, secret_config)

        assert challenge.id
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_CANCELLED_BY_SERVER,
            Id(id=challenge.id),
            OutgoingChallengesEventChannel(user_ref=challenge.caller_ref)
        )
