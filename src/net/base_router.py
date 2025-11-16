from fastapi import BackgroundTasks, Response, Request
from fastapi.datastructures import Headers
from sqlmodel import Session
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from fastapi.routing import APIRoute
from typing import Callable

from src.net.core import App
from src.common.constants import USER_TOKEN_HEADER

import json
import src.log.models as log_models


def headers_to_str(headers: Headers) -> str:
    try:
        return json.dumps(dict(headers.items()), ensure_ascii=False)
    except Exception:
        return "unparsable"


def request_body_to_str(body: bytes) -> str:
    try:
        if not body:
            return "missing"
        elif len(body) > 4000:
            return "too_long"
        else:
            return body.decode()
    except Exception:
        return "unparsable"


def response_body_to_str(body: bytes) -> str:
    if len(body) > 4000:
        return "too_long"
    else:
        try:
            return body.decode()
        except Exception:
            return "unparsable"


def get_client_ref(request: Request, app: App) -> str | None:
    token = request.headers.get(USER_TOKEN_HEADER)
    if token:
        user_ref = app.mutable_state.token_to_user.get(token)
        return user_ref.reference if user_ref else None
    return None


async def log_info(request: Request, response_code: int, response_body: bytes, app: App):
    with Session(app.db_engine) as session:
        request_entry = log_models.RESTRequestLog(
            client_host=request.client.host if request.client else "unknown",
            authorized_as=get_client_ref(request, app),
            endpoint=request.url.path,
            method=request.method,
            headers_json=headers_to_str(request.headers),
            payload=request_body_to_str(await request.body()),
        )
        response_entry = log_models.RESTResponseLog(
            response_code=response_code,
            response=response_body_to_str(response_body),
            request=request_entry
        )
        session.add(request_entry)
        session.add(response_entry)
        session.commit()


class LoggingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response = await original_route_handler(request)
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
                task = BackgroundTask(log_info, request, response.status_code, response.body, request.app)

            if existing_task:
                response.background = BackgroundTasks([existing_task, task])
            else:
                response.background = task

            return response

        return custom_route_handler
