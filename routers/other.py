from fastapi import APIRouter, Response

from globalstate import GlobalState
from models import CompatibilityCheckPayload, CompatibilityResolution, CompatibilityResponse

router = APIRouter(prefix="")


@router.post("/check_compatibility", response_model=CompatibilityResponse)
async def check_compatibility(*, payload: CompatibilityCheckPayload, response: Response):
    resolution = CompatibilityResolution.COMPATIBLE
    if payload.client_build < GlobalState.main_config.min_client_build:
        response.status_code = 400
        resolution = CompatibilityResolution.OUTDATED_CLIENT
    elif payload.min_server_build > GlobalState.main_config.server_build:
        response.status_code = 500
        resolution = CompatibilityResolution.OUTDATED_SERVER

    return CompatibilityResponse(
        resolution=resolution,
        min_client_build=GlobalState.main_config.min_client_build,
        server_build=GlobalState.main_config.server_build
    )
