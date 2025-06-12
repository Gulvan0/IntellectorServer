from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from jinja2 import Template
from pydantic import BaseModel, ValidationError

from database import create_db_and_tables
from globalstate import GlobalState
from models import *  # noqa
from models import EVERYONE, GamePublic

import yaml  # type: ignore


@dataclass(frozen=True)
class WebsocketOutgoingEvent[T: BaseModel]:
    name: str
    payload_type: type[T]
    title: str | None = None
    summary: str | None = None
    description: str | None = None


class WebsocketOutgoingEventRegistry(WebsocketOutgoingEvent, Enum):
    GAME_STARTED = WebsocketOutgoingEvent(
        "game_started",
        GamePublic,
        "Game Started",
        "Broadcasted to `player/started_games` channel whenever a new game involving a respective player starts"
    )

    @classmethod
    def generate_asyncapi_specification(cls) -> dict[str, Any]:
        result = {}
        for outgoing_event in cls:
            payload_type: type[BaseModel] = outgoing_event.payload_type
            result[outgoing_event.name] = dict(
                name=outgoing_event.name,
                title=outgoing_event.title,
                summary=outgoing_event.summary,
                description=outgoing_event.description,
                payload=payload_type.model_json_schema()
            )
        return result


@dataclass(frozen=True)
class WebSocketException(Exception):
    message: str
    kind: str = "processing_error"


@dataclass
class WebSocketWrapper:
    ws: WebSocket
    uuid: UUID = field(default_factory=uuid4)
    saved_token: str | None = None

    def __post_init__(self):
        self.send_json = self.ws.send_json

    async def send_event[T: BaseModel](self, event: WebsocketOutgoingEvent[T], payload: T) -> None:
        await self.ws.send_json(dict(
            event=event.name,
            body=payload.model_dump()
        ))

    async def send_error(self, error: str, details: Any):
        await self.ws.send_json(dict(
            error=error,
            details=details
        ))


type WebSocketIncomingEventHandlerCallable[T:BaseModel] = Callable[[WebSocketWrapper, T], Coroutine[Any, Any, None]]


@dataclass
class WebSocketIncomingEventHandler[T:BaseModel]:
    payload_type: type[T]
    handler_callable: WebSocketIncomingEventHandlerCallable[T]
    title: str | None
    summary: str | None
    description: str | None

    async def handle(self, ws: WebSocketWrapper, payload_json: Any) -> None:
        try:
            payload = self.payload_type.model_validate(payload_json)
        except ValidationError as e:
            await ws.send_error("validation_error", e.errors())
            return

        try:
            await self.handler_callable(ws, payload)
        except WebSocketException as e:
            await ws.send_error(e.kind, e.message)


@dataclass
class WebSocketHandlerCollection:
    _slug_to_handler: dict[str, WebSocketIncomingEventHandler] = field(default_factory=dict)

    @classmethod
    def union(cls, collections: list[WebSocketHandlerCollection]) -> WebSocketHandlerCollection:
        return WebSocketHandlerCollection({
            slug: handler
            for collection in collections
            for slug, handler in collection._slug_to_handler.items()
        })

    def register[T:BaseModel](
        self,
        payload_type: type[T],
        *,
        slug: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        description: str | None = None
    ):
        def decorator(handler_callable: WebSocketIncomingEventHandlerCallable[T]) -> WebSocketIncomingEventHandlerCallable[T]:
            actual_slug = slug or handler_callable.__name__
            assert actual_slug not in self._slug_to_handler
            self._slug_to_handler[actual_slug] = WebSocketIncomingEventHandler(payload_type, handler_callable, title, summary, description)
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

    def generate_asyncapi_specification(self) -> dict[str, Any]:
        result = {}
        for name, incoming_event in self._slug_to_handler.items():
            payload_type: type[BaseModel] = incoming_event.payload_type
            result[name] = dict(
                name=name,
                title=incoming_event.title,
                summary=incoming_event.summary,
                description=incoming_event.description,
                payload=payload_type.model_json_schema()
            )
        return result


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

        self.regenerate_asyncapi_docs()

        self.add_api_route("/ws_docs", self.websocket_docs_endpoint, response_class=HTMLResponse)
        self.add_websocket_route("/ws", self.websocket_endpoint)

    def regenerate_asyncapi_docs(self) -> None:
        incoming_spec = self.ws_handlers.generate_asyncapi_specification()
        outgoing_spec = WebsocketOutgoingEventRegistry.generate_asyncapi_specification()

        resource_dir = Path('./resources/asyncapi')
        document_base = resource_dir / 'document_base.yaml'
        page_template = resource_dir / 'docs_page_template.html'
        output_file = resource_dir / 'docs_page.html'

        document = yaml.safe_load(document_base.read_text())
        document["channels"]["/"]["publish"]["message"]["oneOf"] = list(incoming_spec.keys())
        document["channels"]["/"]["subscribe"]["message"]["oneOf"] = list(outgoing_spec.keys())
        document["components"]["messages"] = incoming_spec | outgoing_spec

        result = Template(page_template.read_text()).render(schema=document)
        output_file.write_text(result)

    async def websocket_docs_endpoint(self):
        return HTMLResponse(content=Path('./resources/asyncapi/docs_page.html').read_text())

    async def websocket_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        ws_wrapper = WebSocketWrapper(websocket)
        GlobalState.ws_subscribers.subscribe(ws_wrapper, EVERYONE)
        try:
            while True:
                data = await websocket.receive_json()
                await self.ws_handlers.handle(ws_wrapper, data)
        except WebSocketDisconnect:
            GlobalState.ws_subscribers.fully_remove(ws_wrapper)
