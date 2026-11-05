from typing import Any
from fastapi import APIRouter, Request

from challenge.methods.cancel import cancel_all_challenges
from game.methods.get import get_ongoing_finite_game
from log.models import ClientErrorLog
from net.base_router import RateLimitedRoute, get_client_ref, rate_limited
from net.rate_limit import RateLimitGroup, client_host
from other.api_version import API_VERSION
from other.models import ClientErrorReport, MutableStatePublic, MutableStateRequestPayload, VersionResponse
from common.dependencies import MutableStateDependency, SecretConfigDependency, SessionDependency, CLIENT_IS_ADMIN_DEPENDENCY
from pubsub.models.channel import EveryoneEventChannel
from pubsub.outgoing_event.update import ServerShutdown


router = APIRouter(prefix="", route_class=RateLimitedRoute)


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    return VersionResponse(api=API_VERSION)


@router.get("/health")
async def get_health(session: SessionDependency) -> dict[str, str]:
    """Stays healthy while the server is draining: a drain is not a failure"""
    await session.exec_raw("SELECT 1")
    return {"status": "ok"}


@router.post("/client_error")
@rate_limited(RateLimitGroup.CLIENT_ERROR)
async def report_client_error(*, session: SessionDependency, request: Request, payload: ClientErrorReport) -> None:
    session.add(ClientErrorLog(
        client_host=client_host(request.client),
        authorized_as=get_client_ref(request, request.app),
        build_id=payload.build_id,
        page_path=payload.page_path,
        message=payload.message,
        stack=payload.stack
    ))
    await session.commit()


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

    if not await get_ongoing_finite_game(session):
        state.exit_event.set()


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
