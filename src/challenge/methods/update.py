from collections import defaultdict
from sqlmodel import select
from challenge.datatypes import ChallengeKind
from challenge.models import Challenge
from common.models import Id, IdList
from common.user_ref import UserReference
from config.models import SecretConfig
from net.core import MutableState
from sqlmodel.sql.expression import SelectOfScalar

import notification.methods as notification_methods
from pubsub.models.channel import IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel
from pubsub.outgoing_event.base import OutgoingEvent
from pubsub.outgoing_event.update import (
    IncomingChallengeCancelled,
    IncomingChallengesCancelledByServer,
    OutgoingChallengesCancelledByServer,
    PublicChallengeCancelled,
    PublicChallengesCancelledByServer,
)
from utils.async_orm_session import AsyncSession


async def cancel_challenge(challenge: Challenge, session: AsyncSession, state: MutableState, secret_config: SecretConfig) -> None:
    assert challenge.id

    await notification_methods.delete_new_public_challenge_notifications(
        challenge_id=challenge.id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    challenge.active = False

    cancel_event_payload = Id(id=challenge.id)
    if challenge.kind == ChallengeKind.PUBLIC:
        event: OutgoingEvent = PublicChallengeCancelled(cancel_event_payload, PublicChallengeListEventChannel())
    elif challenge.kind == ChallengeKind.DIRECT and challenge.callee_ref:
        event = IncomingChallengeCancelled(cancel_event_payload, IncomingChallengesEventChannel(user_ref=challenge.callee_ref))
    await state.ws_subscribers.broadcast(event)


async def cancel_queried_challenges(query: SelectOfScalar[Challenge], session: AsyncSession, state: MutableState, secret_config: SecretConfig):
    cancelled_challenges_by_caller = defaultdict(set)
    cancelled_challenges_by_callee = defaultdict(set)
    cancelled_public_challenges = set()

    challenges = await session.exec(query)
    for challenge in challenges:
        await cancel_challenge(challenge, session, state, secret_config)

        assert challenge.id

        cancelled_challenges_by_caller[challenge.caller_ref].add(challenge.id)
        if challenge.callee_ref:
            cancelled_challenges_by_callee[challenge.callee_ref].add(challenge.id)
        if challenge.kind == ChallengeKind.PUBLIC:
            cancelled_public_challenges.add(challenge.id)

    for caller_ref, challenge_ids in cancelled_challenges_by_caller.items():
        outgoing_channel = OutgoingChallengesEventChannel(user_ref=caller_ref)
        outgoing_event = OutgoingChallengesCancelledByServer(IdList(ids=list(challenge_ids)), outgoing_channel)
        await state.ws_subscribers.broadcast(outgoing_event)

    for callee_ref, challenge_ids in cancelled_challenges_by_callee.items():
        incoming_channel = IncomingChallengesEventChannel(user_ref=callee_ref)
        incoming_event = IncomingChallengesCancelledByServer(IdList(ids=list(challenge_ids)), incoming_channel)
        await state.ws_subscribers.broadcast(incoming_event)

    public_channel = PublicChallengeListEventChannel()
    public_event = PublicChallengesCancelledByServer(IdList(ids=list(cancelled_public_challenges)), public_channel)
    await state.ws_subscribers.broadcast(public_event)


async def cancel_public_challenges_by_caller(caller: UserReference, session: AsyncSession, state: MutableState, secret_config: SecretConfig) -> None:
    await cancel_queried_challenges(
        query=select(Challenge).where(
            Challenge.active == True,  # noqa: E712
            Challenge.kind == ChallengeKind.PUBLIC,
            Challenge.caller_ref == caller.reference,
        ),
        session=session,
        state=state,
        secret_config=secret_config
    )


async def cancel_all_challenges(session: AsyncSession, state: MutableState, secret_config: SecretConfig):
    await cancel_queried_challenges(
        query=select(Challenge).where(Challenge.active == True),  # noqa: E712
        session=session,
        state=state,
        secret_config=secret_config
    )
