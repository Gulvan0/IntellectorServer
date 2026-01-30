from typing import Any
from fastapi import APIRouter, Depends, Response

from challenge.methods.update import cancel_all_challenges
from game.methods.get import get_ongoing_finite_game
from net.base_router import LoggingRoute
from other.datatypes import CompatibilityResolution
from other.models import CompatibilityCheckPayload, CompatibilityResponse
from common.dependencies import MainConfigDependency, MutableStateDependency, SecretConfigDependency, SessionDependency, verify_admin
from pubsub.models.channel import EveryoneEventChannel
from pubsub.outgoing_event.update import ServerShutdown


router = APIRouter(prefix="", route_class=LoggingRoute)


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


@router.post("/shutdown", dependencies=[Depends(verify_admin)])
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


@router.get("/mutable_state", dependencies=[Depends(verify_admin)])
async def get_mutable_state(state: MutableStateDependency) -> Any:
    raise NotImplementedError()  # TODO: Implement
