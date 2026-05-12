import asyncio
import json

from fastapi import BackgroundTasks, HTTPException, Response, Request
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from fastapi.routing import APIRoute
from typing import Callable

from log.models import RESTRequestLog, RESTResponseLog
from net.core import App
from common.constants import USER_TOKEN_HEADER

from net.utils.log_codecs import dump_headers, dump_bytes
from utils.async_orm_session import AsyncSession


def get_client_ref(request: Request, app: App) -> str | None:
    token = request.headers.get(USER_TOKEN_HEADER)
    if token:
        user_ref = app.mutable_state.token_to_user.get(token)
        return user_ref.reference if user_ref else None
    return None


async def log_info(request: Request, response_code: int, response_body: bytes, app: App) -> None:
    async with AsyncSession(app.db_engine) as session:
        request_entry = RESTRequestLog(
            client_host=request.client.host if request.client else "unknown",
            authorized_as=get_client_ref(request, app),
            endpoint=request.url.path,
            method=request.method,
            headers_json=dump_headers(request.headers),
            payload=dump_bytes(await request.body()),
        )
        response_entry = RESTResponseLog(
            response_code=response_code,
            response=dump_bytes(response_body),
            request=request_entry
        )
        session.add(request_entry)
        session.add(response_entry)
        await session.commit()


class LoggingRoute(APIRoute):
    def get_route_handler(self) -> Callable:  # type: ignore[type-arg]
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                response = await original_route_handler(request)
            except HTTPException as exc:
                body = json.dumps({"detail": exc.detail}).encode()
                request.app.mutable_state.delayed_tasks.plan(log_info(request, exc.status_code, body, request.app))
                raise
            except Exception as exc:
                body = json.dumps({"detail": str(exc)}).encode()
                request.app.mutable_state.delayed_tasks.plan(log_info(request, 500, body, request.app))
                raise
            existing_task = response.background

            if isinstance(response, StreamingResponse):
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                response_body = b''.join(chunks)  # type: ignore

                task = BackgroundTask(log_info, request, response.status_code, response_body, request.app)
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            else:
                task = BackgroundTask(log_info, request, response.status_code, response.body, request.app)  # type: ignore[arg-type]

            if existing_task:
                response.background = BackgroundTasks([existing_task, task])
            else:
                response.background = task

            return response

        return custom_route_handler
