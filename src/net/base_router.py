from datetime import UTC, datetime
import json

from fastapi import BackgroundTasks, HTTPException, Response, Request
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy import update
from sqlmodel import col
from typing import Any, Callable, TypeVar

from log.datatypes import RestMethod
from log.models import RESTRequestLog
from net.core import App
from common.constants import USER_TOKEN_HEADER

from net.utils.log_codecs import dump_headers, dump_bytes
from net.rate_limit import RateLimitGroup, client_host
from net.utils.rest_error import RestException, rate_limited_error
from utils.async_orm_session import AsyncSession


IP_KEYED_GROUPS = {RateLimitGroup.SIGNIN, RateLimitGroup.REGISTRATION, RateLimitGroup.GUEST}  # their callers aren't authorized yet


def get_client_ref(request: Request, app: App) -> str | None:
    token = request.headers.get(USER_TOKEN_HEADER)
    if token:
        user_ref = app.mutable_state.token_to_user.get(token)
        return user_ref.reference if user_ref else None
    return None


async def log_request(request: Request, app: App) -> int | None:
    """Commits the request before it is handled, so a request that crashes or hangs the server is still logged.
    Returns the log entry's id, or None if the method isn't logged"""
    try:
        method = RestMethod(request.method.lower())
    except ValueError:
        return None

    async with AsyncSession(app.db_engine) as session:
        request_entry = RESTRequestLog(
            client_host=client_host(request.client),
            authorized_as=get_client_ref(request, app),
            endpoint=request.url.path,
            method=method,
            headers_json=dump_headers(request.headers),
            payload=dump_bytes(await request.body()),
        )
        session.add(request_entry)
        await session.flush()
        request_id = request_entry.id  # read before commit, which expires the entry's attributes
        await session.commit()
        return request_id


async def log_response(request_id: int | None, response_code: int, response_body: bytes, app: App) -> None:
    if request_id is None:
        return

    async with AsyncSession(app.db_engine) as session:
        connection = await session.connection()
        await connection.execute(
            update(RESTRequestLog)
            .where(col(RESTRequestLog.id) == request_id)
            .values(response_code=response_code, response=dump_bytes(response_body))
        )
        await session.commit()


Endpoint = TypeVar("Endpoint", bound=Callable[..., Any])


def game_action(endpoint: Endpoint) -> Endpoint:
    """Marks an endpoint changing the game named by its payload's `game_id`: requests to such endpoints run one at a time
    per game, their dependencies included. `request.state.arrived_at` tells when the request came, before waiting for its turn"""
    setattr(endpoint, "is_game_action", True)
    return endpoint


async def run_game_action(request: Request, handler: Callable[[Request], Any], arrived_at: datetime) -> Response:
    request.state.arrived_at = arrived_at
    try:
        game_id = json.loads(await request.body()).get("game_id")
    except (ValueError, AttributeError):
        game_id = None

    if not isinstance(game_id, int):
        return await handler(request)  # rejected by the payload's validation

    async with request.app.mutable_state.game_action(game_id):
        return await handler(request)


def rate_limited(group: RateLimitGroup) -> Callable[[Endpoint], Endpoint]:
    """Makes an endpoint spend the budget of `group` instead of the general one"""
    def decorator(endpoint: Endpoint) -> Endpoint:
        setattr(endpoint, "rate_limit_group", group)
        return endpoint
    return decorator


def get_rate_limit_key(request: Request, group: RateLimitGroup) -> str:
    client_ref = None if group in IP_KEYED_GROUPS else get_client_ref(request, request.app)
    return f"user:{client_ref}" if client_ref else f"ip:{client_host(request.client)}"


class RateLimitedRoute(APIRoute):
    def get_route_handler(self) -> Callable:  # type: ignore[type-arg]
        unlimited_route_handler = self.get_unlimited_route_handler()
        group: RateLimitGroup = getattr(self.endpoint, "rate_limit_group", RateLimitGroup.GENERAL)

        async def limited_route_handler(request: Request) -> Response:
            retry_after_secs = request.app.rate_limiter.take(group, get_rate_limit_key(request, group))
            if retry_after_secs is not None:
                raise rate_limited_error(retry_after_secs)
            return await unlimited_route_handler(request)

        return limited_route_handler

    def get_unlimited_route_handler(self) -> Callable:  # type: ignore[type-arg]
        return super().get_route_handler()


class LoggingRoute(RateLimitedRoute):
    """The limit is checked first: a flood of rejected requests must not turn into a flood of writes to the log"""

    def get_unlimited_route_handler(self) -> Callable:  # type: ignore[type-arg]
        original_route_handler = super().get_unlimited_route_handler()
        is_game_action = getattr(self.endpoint, "is_game_action", False)

        async def custom_route_handler(request: Request) -> Response:
            arrived_at = datetime.now(UTC)
            await request.body()  # Cache the request's body
            request_id = await log_request(request, request.app)

            try:
                if is_game_action:
                    response = await run_game_action(request, original_route_handler, arrived_at)
                else:
                    response = await original_route_handler(request)
            except HTTPException as exc:
                body = json.dumps(exc.body() if isinstance(exc, RestException) else {"detail": exc.detail}).encode()
                request.app.mutable_state.concurrent_tasks.plan(log_response(request_id, exc.status_code, body, request.app))
                raise
            except Exception as exc:
                body = json.dumps({"detail": str(exc)}).encode()
                request.app.mutable_state.concurrent_tasks.plan(log_response(request_id, 500, body, request.app))
                raise
            existing_task = response.background

            if isinstance(response, StreamingResponse):
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                response_body = b''.join(chunks)  # type: ignore

                task = BackgroundTask(log_response, request_id, response.status_code, response_body, request.app)
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            else:
                task = BackgroundTask(log_response, request_id, response.status_code, response.body, request.app)  # type: ignore[arg-type]

            if existing_task:
                response.background = BackgroundTasks([existing_task, task])
            else:
                response.background = task

            return response

        return custom_route_handler
