from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select
from src.challenge.datatypes import ChallengeKind
from src.challenge.methods.get import get_direct_challenges
from src.challenge.methods.merge import try_merging
from src.challenge.methods.validation import perform_common_validations, validate_direct_callee
from src.challenge.methods.update import cancel_challenge as cancel_specific_challenge
from src.challenge.models import Challenge, ChallengeCreateDirect, ChallengeCreateOpen, ChallengeCreateResponse, ChallengePublic
from src.challenge.methods.cast import to_public_challenge
from src.common.dependencies import MainConfigDependency, MandatoryUserDependency, MutableStateDependency, SecretConfigDependency, SessionDependency
from src.common.models import Id
from src.net.base_router import LoggingRoute
from src.net.outgoing import WebsocketOutgoingEventRegistry
from src.net.utils.early_response import supports_early_responses
from src.pubsub.models import IncomingChallengesEventChannel, OutgoingChallengesEventChannel, PublicChallengeListEventChannel

import src.notification.methods as notification_methods
import src.game.methods.cast as game_cast_methods
import src.game.methods.create as game_create_methods
import src.game.models.main as game_models


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
):
    await perform_common_validations(challenge, caller, state.shutdown_activated, main_config.limits, session)
    await try_merging(challenge, caller, session, state, secret_config)

    db_challenge = challenge.to_db_challenge(caller.reference)
    session.add(db_challenge)
    await session.commit()

    public_challenge = db_challenge.to_public(None)

    if not challenge.link_only:
        await state.ws_subscribers.broadcast(
            WebsocketOutgoingEventRegistry.NEW_PUBLIC_CHALLENGE,
            public_challenge,
            PublicChallengeListEventChannel()
        )

        await notification_methods.send_new_public_challenge_notifications(
            caller=caller,
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
):
    await perform_common_validations(challenge, caller, state.shutdown_activated, main_config.limits, session)
    callee = await validate_direct_callee(challenge, caller, state.last_guest_id, session)
    await try_merging(challenge, caller, session, state, secret_config)

    direct_challenges_observer_channel = IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
    callee_online = state.has_user_subscriber(callee, direct_challenges_observer_channel)

    db_challenge = challenge.to_db_challenge(caller.reference)
    session.add(db_challenge)
    await session.commit()

    public_challenge = db_challenge.to_public(None)
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.INCOMING_CHALLENGE_RECEIVED,
        public_challenge,
        IncomingChallengesEventChannel(user_ref=challenge.callee_ref)
    )
    return ChallengeCreateResponse(result="created", challenge=public_challenge, callee_online=callee_online)


@router.get("/public", response_model=list[ChallengePublic])
async def get_public_challenges(*, session: SessionDependency, offset: int = 0, limit: int = Query(default=50, le=50)):
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
async def get_my_direct_challenges(*, session: SessionDependency, client: MandatoryUserDependency):
    return [
        await to_public_challenge(session, challenge)
        for challenge in await get_direct_challenges(session, client)
    ]


@router.get("/{id}", response_model=ChallengePublic)
async def get_challenge(*, session: SessionDependency, id: int):
    db_challenge = await session.get(Challenge, id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    resulting_game = None
    if db_challenge.resulting_game:
        resulting_game = await game_cast_methods.to_public_game(session, db_challenge.resulting_game)

    return db_challenge.to_public(resulting_game)


@router.delete("/{id}")
async def cancel_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=400, detail="Challenge is already inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.caller_ref != client.reference:
        raise HTTPException(status_code=403, detail="Only the author of this challenge may cancel it")

    await cancel_specific_challenge(db_challenge, session, state, secret_config)
    session.add(db_challenge)
    await session.commit()


@router.post("/{id}/accept", response_model=game_models.GamePublic)
async def accept_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=400, detail="Challenge is inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.kind == ChallengeKind.DIRECT:
        if db_challenge.callee_ref != client.reference:
            raise HTTPException(status_code=403, detail="You are not the recepient of this challenge")
    else:
        if db_challenge.caller_ref == client.reference:
            raise HTTPException(status_code=400, detail="Cannot accept own challenge")

    db_game = await game_create_methods.create_internal_game(db_challenge, client, session, state, secret_config)

    return db_game


@router.post("/{id}/decline")
async def decline_challenge(
    *,
    challenge_id: int,
    session: SessionDependency,
    client: MandatoryUserDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    db_challenge = await session.get(Challenge, challenge_id)

    if not db_challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if not db_challenge.active:
        raise HTTPException(status_code=400, detail="Challenge is inactive (i.e. cancelled, accepted or rejected)")

    if db_challenge.kind != ChallengeKind.DIRECT:
        raise HTTPException(status_code=400, detail="Cannot decline an open challenge")

    if db_challenge.callee_ref != client.reference:
        raise HTTPException(status_code=403, detail="You are not the recepient of this challenge")

    db_challenge.active = False
    session.add(db_challenge)

    await notification_methods.delete_new_public_challenge_notifications(
        challenge_id=challenge_id,
        session=session,
        vk_token=secret_config.integrations.vk.token
    )

    await session.commit()

    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.OUTGOING_CHALLENGE_REJECTED,
        Id(id=challenge_id),
        OutgoingChallengesEventChannel(user_ref=db_challenge.caller_ref)
    )
