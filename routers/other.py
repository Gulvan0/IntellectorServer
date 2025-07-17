from fastapi import APIRouter, Depends, Response

from models import CompatibilityCheckPayload, CompatibilityResolution, CompatibilityResponse
from models.other import EmptyModel
from net.outgoing import WebsocketOutgoingEventRegistry
from routers.challenge import cancel_all_challenges
from routers.shared_queries.game import get_ongoing_finite_game
from routers.utils import MainConfigDependency, MutableStateDependency, SecretConfigDependency, SessionDependency, verify_admin

router = APIRouter(prefix="")


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
    await cancel_all_challenges(session, state, secret_config)
    await state.ws_subscribers.broadcast(
        WebsocketOutgoingEventRegistry.SERVER_SHUTDOWN,
        EmptyModel()
    )

    if not get_ongoing_finite_game(session):
        raise KeyboardInterrupt
