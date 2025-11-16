from fastapi import APIRouter, Depends, Response

from src.net.base_router import LoggingRoute
from src.other.models import CompatibilityCheckPayload, CompatibilityResolution, CompatibilityResponse
from src.common.models import EmptyModel
from src.common.dependencies import MainConfigDependency, MutableStateDependency, SecretConfigDependency, SessionDependency, verify_admin
from src.net.outgoing import WebsocketOutgoingEventRegistry

import src.challenge.methods.update as challenge_update_methods
import src.game.methods.get as game_get_methods


router = APIRouter(prefix="", route_class=LoggingRoute)


@router.post("/check_compatibility", response_model=CompatibilityResponse)
async def check_compatibility(*, payload: CompatibilityCheckPayload, response: Response, main_config: MainConfigDependency):
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


@router.get("/shutdown", dependencies=[Depends(verify_admin)])
async def shutdown(
    *,
    session: SessionDependency,
    state: MutableStateDependency,
    secret_config: SecretConfigDependency
):
    if state.shutdown_activated:
        return

    state.shutdown_activated = True
    await challenge_update_methods.cancel_all_challenges(session, state, secret_config)
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.SERVER_SHUTDOWN,
        EmptyModel()
    )

    if not game_get_methods.get_ongoing_finite_game(session):
        raise KeyboardInterrupt


@router.get("/mutable_state", dependencies=[Depends(verify_admin)])
async def get_mutable_state(state: MutableStateDependency):
    raise NotImplementedError()  # TODO: Implement
