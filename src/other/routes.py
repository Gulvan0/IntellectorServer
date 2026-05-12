from typing import Any
from fastapi import APIRouter, Response

from challenge.methods.cancel import cancel_all_challenges
from game.methods.get import get_ongoing_finite_game
from other.datatypes import CompatibilityResolution
from other.models import CompatibilityCheckPayload, CompatibilityResponse, MutableStatePublic, MutableStateRequestPayload
from common.dependencies import MainConfigDependency, MutableStateDependency, SecretConfigDependency, SessionDependency, CLIENT_IS_ADMIN_DEPENDENCY
from pubsub.models.channel import EveryoneEventChannel
from pubsub.outgoing_event.update import ServerShutdown


router = APIRouter(prefix="")


@router.post("/check_compatibility", response_model=CompatibilityResponse)
async def check_compatibility(*, payload: CompatibilityCheckPayload, response: Response, main_config: MainConfigDependency) -> CompatibilityResponse:
    resolution = CompatibilityResolution.COMPATIBLE
    if payload.client_build < main_config.min_client_build:
        response.status_code = 400
        resolution = CompatibilityResolution.OUTDATED_CLIENT
    elif payload.min_server_build > main_config.server_build:
        response.status_code = 500
        resolution = CompatibilityResolution.OUTDATED_SERVER

    return CompatibilityResponse(
        resolution=resolution,
        min_client_build=main_config.min_client_build,
        server_build=main_config.server_build
    )


@router.post("/shutdown", dependencies=[CLIENT_IS_ADMIN_DEPENDENCY])
async def shutdown(
    *,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
) -> None:
    if state.shutdown_activated:
        return

    state.shutdown_activated = True
    await cancel_all_challenges(session, state, secret_config)

    event = ServerShutdown(None, EveryoneEventChannel())
    await state.ws_subscribers.broadcast(event)

    if not get_ongoing_finite_game(session):
        raise KeyboardInterrupt  # A hack to break out of the FastAPI jail


@router.get("/mutable_state", response_model=MutableStatePublic, dependencies=[CLIENT_IS_ADMIN_DEPENDENCY])
async def get_mutable_state(*, state: MutableStateDependency, payload: MutableStateRequestPayload) -> Any:
    public_state = MutableStatePublic(
        shutdown_activated=state.shutdown_activated,
        last_guest_id=state.last_guest_id,
        stored_tokens=len(state.token_to_user),
        stored_subs=len(state.ws_subscribers),
        stored_timeout_timers=len(state.game_timeout_check_timers),
        stored_challenge_cancelling_timers=len(state.user_challenge_cancelling_timers)
    )

    if payload.unwrap_tokens:
        public_state.token_to_user = {token: user.reference for token, user in state.token_to_user.straight.items()}

    if payload.unwrap_subs:
        public_state.ws_subscribers = state.ws_subscribers.dump()

    if payload.unwrap_timeout_timers:
        public_state.game_timeout_check_timers = {game_id: timer.when() for game_id, timer in state.game_timeout_check_timers.items()}

    if payload.unwrap_challenge_cancelling_timers:
        public_state.user_challenge_cancelling_timers = {user.reference: timer.when() for user, timer in state.user_challenge_cancelling_timers.items()}

    return public_state
