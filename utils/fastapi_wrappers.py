from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import reduce
from starlette.types import Lifespan
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, FastAPI, WebSocket
from pydantic import BaseModel, ValidationError

from database import create_db_and_tables
from models import *  # noqa


@dataclass
class WebSocketWrapper:
    ws: WebSocket

    def __post_init__(self):
        self.send_json = self.ws.send_json

    async def send_error(self, error: str, details: Any):
        await self.ws.send_json(dict(
            error=error,
            details=details
        ))


type WebSocketEventHandlerCallable[T:BaseModel] = Callable[[WebSocketWrapper, T], Coroutine[Any, Any, None]]


@dataclass
class WebSocketEventHandler[T:BaseModel]:
    payload_type: type[T]
    handler_callable: WebSocketEventHandlerCallable[T]

    async def handle(self, ws: WebSocketWrapper, payload_json: Any) -> None:
        try:
            payload = self.payload_type.model_validate(payload_json)
        except ValidationError as e:
            await ws.send_error("validation_error", e.errors())
        else:
            await self.handler_callable(ws, payload)


@dataclass
class WebSocketHandlerCollection:
    _slug_to_handler: dict[str, WebSocketEventHandler] = field(default_factory=dict)

    @classmethod
    def union(cls, collections: list[WebSocketHandlerCollection]) -> WebSocketHandlerCollection:
        return WebSocketHandlerCollection({
            slug: handler
            for collection in collections
            for slug, handler in collection._slug_to_handler.items()
        })

    def register[T:BaseModel](self, payload_type: type[T], slug: str | None = None):
        def decorator(handler_callable: WebSocketEventHandlerCallable[T]) -> WebSocketEventHandlerCallable[T]:
            actual_slug = slug or handler_callable.__name__
            assert actual_slug not in self._slug_to_handler
            self._slug_to_handler[actual_slug] = WebSocketEventHandler(payload_type, handler_callable)
            return handler_callable
        return decorator

    async def handle(self, ws: WebSocketWrapper, data: Any) -> None:
        if not isinstance(data, dict):
            await ws.send_error("parsing_error", "WebSocket message isn't a dictionary (mapping)")
            return

        event_slug = data.get("event")
        if not event_slug:
            await ws.send_error("parsing_error", "'event' field must be specified (and not null)")
            return

        handler = self._slug_to_handler.get(event_slug)
        if not handler:
            await ws.send_error("unknown_event", f"Event not found: {event_slug}")
            return

        await handler.handle(ws, data.get("body"))


@asynccontextmanager
async def __lifespan(_: FastAPI):
    create_db_and_tables()  # All models were imported using wildcard at the top of this file
    yield


class App(FastAPI):
    def __init__(self, rest_routers: list[APIRouter], ws_collections: list[WebSocketHandlerCollection]) -> None:
        super().__init__(lifespan=__lifespan)

        for router in rest_routers:
            self.include_router(router)

        self.ws_handlers: WebSocketHandlerCollection = WebSocketHandlerCollection.union(ws_collections)

        self.add_websocket_route("/ws", self.websocket_endpoint)

    async def websocket_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        ws_wrapper = WebSocketWrapper(websocket)
        while True:
            data = await websocket.receive_json()
            await self.ws_handlers.handle(ws_wrapper, data)
