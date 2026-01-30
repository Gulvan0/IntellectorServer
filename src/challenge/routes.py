from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select
from challenge.datatypes import ChallengeKind
from challenge.methods.get import get_direct_challenges
from challenge.methods.merge import try_merging
from challenge.methods.validation import perform_common_validations, validate_direct_callee
from challenge.methods.update import cancel_challenge as cancel_specific_challenge
from challenge.models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse, ChallengePublic
from challenge.methods.cast import to_public_challenge
from common.dependencies import MainConfigDependency, MandatoryUserDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from common.models import Id
from game.methods.create import create_internal_game
from game.models.main import GamePublic
from net.base_router import LoggingRoute
from net.utils.early_response import supports_early_responses
from notification.methods import delete_new_public_challenge_notifications, send_new_public_challenge_notifications
from pubsub.models.channel import IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel
from pubsub.outgoing_event.update import IncomingChallengeReceived, NewPublicChallenge, OutgoingChallengeRejected


router = APIRouter(prefix="/challenge", route_class=LoggingRoute)


@supports_early_responses()
@router.post("/create/open", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_open_challenge(
    *,
    challenge: ChallengeCreateOpen,
    session: SessionDependency,
    caller: MandatoryUserDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency
) -> ChallengeCreateResponse:
    await perform_common_validations(challenge, caller, state.shutdown_activated, main_config.limits, session)
    await try_merging(challenge, caller, session, state, secret_config)

    db_challenge = challenge.to_db_challenge(caller.reference)
    session.add(db_challenge)
    await session.commit()

    public_challenge = await to_public_challenge(session, db_challenge)

    if not challenge.link_only:
        event = NewPublicChallenge(public_challenge, PublicChallengeListEventChannel())
        await state.ws_subscribers.broadcast(event)

        await send_new_public_challenge_notifications(
            public_challenge=public_challenge,
            integrations_config=secret_config.integrations,
            session=session
        )

    return ChallengeCreateResponse(result="created", challenge=public_challenge)


@supports_early_responses()
@router.post("/create/direct", status_code=201, response_model=ChallengeCreateResponse, response_model_exclude_none=True)
async def create_direct_challenge(
    *,
    challenge: ChallengeCreateDirect,
    session: SessionDependency,
    caller: MandatoryUserDependency,
    state: MutableStateDependency,
    main_config: MainConfigDependency,
    secret_config: SecretConfigDependency
) -> ChallengeCreateResponse:
    await perform_common_validations(challenge, caller, state.shutdown_activated, main_config.limits, session)
    callee = await validate_direct_callee(challenge, caller, state.last_guest_id, session)
    await try_merging(challenge, caller, session, state, secret_config)

    direct_challenges_observer_channel = IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
    callee_online = state.has_user_subscriber(callee, direct_challenges_observer_channel)

    db_challenge = challenge.to_db_challenge(caller.reference)
    session.add(db_challenge)
    await session.commit()

    public_challenge = await to_public_challenge(session, db_challenge)

    event = IncomingChallengeReceived(public_challenge, IncomingChallengesEventChannel(user_ref=challenge.callee_ref))
    await state.ws_subscribers.broadcast(event)

    return ChallengeCreateResponse(result="created", challenge=public_challenge, callee_online=callee_online)


@router.get("/public", response_model=list[ChallengePublic])
async def get_public_challenges(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=50, le=50)) -> list[ChallengePublic]:
    challenges_result = await session.exec(select(
        Challenge
    ).where(
        Challenge.active == True,  # noqa
        Challenge.kind == ChallengeKind.PUBLIC
    ).offset(offset).limit(limit))

    return [
        await to_public_challenge(session, challenge)
        for challenge in challenges_result.all()
    ]


@router.get("/my_direct", response_model=list[ChallengePublic])
async def get_my_direct_challenges(*, session: SessionDependency, client: MandatoryUserDependency) -> list[ChallengePublic]:
    return [
        await to_public_challenge(session, challenge)
        for challenge in await get_direct_challenges(session, client)
    ]


@router.get("/{id}", response_model=ChallengePublic)
async def get_challenge(*, session: SessionDependency, id: int) -> ChallengePublic:
    db_challenge = await session.get(Challenge, id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return await to_public_challenge(session, db_challenge)


@router.delete("/{id}")
async def cancel_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
) -> None:
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=422, detail="Challenge is already inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.caller_ref != client.reference:
        raise HTTPException(status_code=403, detail="Only the author of this challenge may cancel it")

    await cancel_specific_challenge(db_challenge, session, state, secret_config)
    session.add(db_challenge)
    await session.commit()


@router.post("/{id}/accept", response_model=GamePublic)
async def accept_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
) -> GamePublic:
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=422, detail="Challenge is inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.kind == ChallengeKind.DIRECT:
        if db_challenge.callee_ref != client.reference:
            raise HTTPException(status_code=403, detail="You are not the recepient of this challenge")
    else:
        if db_challenge.caller_ref == client.reference:
            raise HTTPException(status_code=422, detail="Cannot accept own challenge")

    db_game = await create_internal_game(db_challenge, client, session, state, secret_config)

    return db_game


@router.post("/{id}/decline")
async def decline_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
) -> None:
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=422, detail="Challenge is inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.kind != ChallengeKind.DIRECT:
        raise HTTPException(status_code=422, detail="Cannot decline an open challenge")

    if db_challenge.callee_ref != client.reference:
        raise HTTPException(status_code=403, detail="You are not the recepient of this challenge")

    db_challenge.active = False
    session.add(db_challenge)

    await delete_new_public_challenge_notifications(
        challenge_id=challenge_id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    await session.commit()

    event = OutgoingChallengeRejected(Id(id=challenge_id), OutgoingChallengesEventChannel(user_ref=db_challenge.caller_ref))
    await state.ws_subscribers.broadcast(event)
