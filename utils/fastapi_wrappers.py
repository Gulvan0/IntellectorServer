from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from jinja2 import Template
from pydantic import BaseModel, ValidationError

from database import create_db_and_tables
from globalstate import GlobalState
if TYPE_CHECKING:
    from models import (
        GamePublic,
        ChallengePublic,
        Id,
        GameStartedBroadcastedData,
        GameEndedBroadcastedData,
        StartedPlayerGamesEventChannel,
        PublicChallengeListEventChannel,
        GameListEventChannel,
        IncomingChallengesEventChannel,
        OutgoingChallengesEventChannel,
        EventChannel,
        EveryoneEventChannel,
    )
else:
    from models import *  # noqa

import yaml  # type: ignore


@dataclass(frozen=True)
class WebsocketOutgoingEvent[T: BaseModel, C: EventChannel]:
    event_name: str
    payload_type: type[T]
    target_channel_class: type[C] | None
    title: str | None = None
    summary: str | None = None
    description: str | None = None


class WebsocketOutgoingEventRegistry(WebsocketOutgoingEvent, Enum):
    GAME_STARTED = (
        "game_started",
        GamePublic,
        StartedPlayerGamesEventChannel,
        "Game Started (for player's followers)",
        "Broadcasted to `player.started_games` channel group whenever a new game involving a respective player starts"
    )

    NEW_PUBLIC_CHALLENGE = (
        "new_public_challenge",
        ChallengePublic,
        PublicChallengeListEventChannel,
        "New Public Challenge",
        "Broadcasted to `public_challenge_list` channel group whenever a new public challenge is created"
    )

    PUBLIC_CHALLENGE_CANCELLED = (
        "public_challenge_cancelled",
        Id,
        PublicChallengeListEventChannel,
        "Public Challenge Cancelled",
        "Broadcasted to `public_challenge_list` channel group whenever a public challenge is cancelled"
    )

    PUBLIC_CHALLENGE_FULFILLED = (
        "public_challenge_fulfilled",
        Id,
        PublicChallengeListEventChannel,
        "Public Challenge Fulfilled",
        "Broadcasted to `public_challenge_list` channel group whenever a public challenge is fulfilled (i.e. accepted by someone)"
    )

    NEW_ACTIVE_GAME = (
        "new_active_game",
        GameStartedBroadcastedData,
        GameListEventChannel,
        "Game Started (for game lists watchers)",
        "Broadcasted to `game_list` channel group whenever a new game starts"
    )

    NEW_RECENT_GAME = (
        "new_recent_game",
        GameEndedBroadcastedData,
        GameListEventChannel,
        "Game Ended (for game lists watchers)",
        "Broadcasted to `game_list` channel group whenever a game ends"
    )

    INCOMING_CHALLENGE_RECEIVED = (
        "incoming_challenge_received",
        ChallengePublic,
        IncomingChallengesEventChannel,
        "Incoming Challenge Received",
        "Broadcasted to `incoming_challenges` channel group whenever a direct challenge arrives"
    )

    INCOMING_CHALLENGE_CANCELLED = (
        "incoming_challenge_cancelled",
        Id,
        IncomingChallengesEventChannel,
        "Incoming Challenge Cancelled",
        "Broadcasted to `incoming_challenges` channel group whenever an incoming direct challenge is cancelled"
    )

    OUTGOING_CHALLENGE_ACCEPTED = (
        "outgoing_challenge_accepted",
        Id,
        OutgoingChallengesEventChannel,
        "Outgoing Challenge Accepted",
        "Broadcasted to `outgoing_challenges` channel group whenever an outgoing (direct or open) challenge is accepted"
    )

    OUTGOING_CHALLENGE_REJECTED = (
        "outgoing_challenge_rejected",
        Id,
        OutgoingChallengesEventChannel,
        "Outgoing Challenge Rejected",
        "Broadcasted to `outgoing_challenges` channel group whenever an outgoing direct challenge is rejected"
    )

    @classmethod
    def generate_asyncapi_specification(cls) -> dict[str, Any]:
        result = dict(
            channels={},
            operations={},
            components=dict(
                messages={}
            )
        )
        for outgoing_event in cls:
            channel_class: type[EventChannel] = outgoing_event.target_channel_class
            channel_group = channel_class.group
            msg_ref = {"$ref": f"#/components/messages/{outgoing_event.event_name}"}
            if channel_group not in result["channels"]:
                result["channels"][channel_group] = dict(address=channel_group, messages={})
                result["operations"][channel_group] = dict(action="send", messages=[], channel={
                    "$ref": f"#/channels/{channel_group}"
                })
            result["channels"][channel_group]["messages"][outgoing_event.event_name] = msg_ref
            result["operations"][channel_group]["messages"].append({
                "$ref": f"#/channels/{channel_group}/messages/{outgoing_event.event_name}"
            })

            payload_type: type[BaseModel] = outgoing_event.payload_type
            msg_definition = dict(
                name=outgoing_event.event_name,
                payload=payload_type.model_json_schema(ref_template=f'#/components/messages/{outgoing_event.event_name}/payload/$defs/{{model}}')
            )
            if outgoing_event.title:
                msg_definition["title"] = outgoing_event.title
            if outgoing_event.summary:
                msg_definition["summary"] = outgoing_event.summary
            if outgoing_event.description:
                msg_definition["description"] = outgoing_event.description
            result["components"]["messages"][outgoing_event.event_name] = msg_definition
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

    async def send_event[T: BaseModel, C: EventChannel](self, event: WebsocketOutgoingEvent[T, C], payload: T, channel: C | None = None) -> None:
        await self.ws.send_json(dict(
            event=event.event_name,
            channel=channel.model_dump(),
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
        # TODO: Implement user forwarding
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

        # TODO: Validate model using pydantic, get user by token (or call send_error and skip), pass user-based model
        # if "token" in data and data["token"] != ws_wrapper.saved_token:
        #     GlobalState.token_to_user.get(...)...

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
        result = dict(
            channels=dict(
                NO_CHANNEL=dict(
                    messages={}
                )
            ),
            operations=dict(
                receive=dict(
                    action="receive",
                    channel={
                        "$ref": "#/channels/NO_CHANNEL"
                    },
                    messages=[]
                )
            ),
            components=dict(
                messages={}
            )
        )
        for name, incoming_event in self._slug_to_handler.items():
            msg_ref = {"$ref": f"#/components/messages/{name}"}
            result["channels"]["NO_CHANNEL"]["messages"][name] = msg_ref
            result["operations"]["receive"]["messages"].append({
                "$ref": f"#/channels/NO_CHANNEL/messages/{name}"
            })

            payload_type: type[BaseModel] = incoming_event.payload_type
            msg_definition = dict(
                name=name,
                payload=payload_type.model_json_schema(ref_template=f'#/components/messages/{name}/payload/$defs/{{model}}')
            )
            if incoming_event.title:
                msg_definition["title"] = incoming_event.title
            if incoming_event.summary:
                msg_definition["summary"] = incoming_event.summary
            if incoming_event.description:
                msg_definition["description"] = incoming_event.description
            result["components"]["messages"][name] = msg_definition
        return result


class App(FastAPI):
    @asynccontextmanager
    async def __lifespan(self: FastAPI):
        create_db_and_tables()  # All models were imported using wildcard at the top of this file
        yield

    def __init__(self, rest_routers: list[APIRouter], ws_collections: list[WebSocketHandlerCollection]) -> None:
        super().__init__(lifespan=App.__lifespan)

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
        output_spec = resource_dir / 'asyncapi_spec.json'

        document = yaml.safe_load(document_base.read_text())
        document.update(outgoing_spec)
        document["channels"].update(incoming_spec["channels"])
        document["operations"].update(incoming_spec["operations"])
        document["components"]["messages"].update(incoming_spec["components"]["messages"])
        document["info"]["description"] = document["info"]["description"].replace('\n', '\\n').replace('"', '\\"')

        output_spec.write_text(json.dumps(document, indent=4, ensure_ascii=False))
        result = Template(page_template.read_text()).render(schema=document)
        output_file.write_text(result)

    async def websocket_docs_endpoint(self):
        return HTMLResponse(content=Path('./resources/asyncapi/docs_page.html').read_text())

    async def websocket_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        ws_wrapper = WebSocketWrapper(websocket)
        GlobalState.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while True:
                data = await websocket.receive_json()
                await self.ws_handlers.handle(ws_wrapper, data)
        except WebSocketDisconnect:
            GlobalState.ws_subscribers.fully_remove(ws_wrapper)
