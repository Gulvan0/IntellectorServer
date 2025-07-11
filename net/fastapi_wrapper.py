from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from jinja2 import Template
from pydantic import BaseModel, ValidationError
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import Engine

from models.channel import EventChannel
from models.config import MainConfig, SecretConfig
from net.incoming import WebSocketHandlerCollection
from net.outgoing import WebsocketOutgoingEvent, WebsocketOutgoingEventRegistry
from net.sub_storage import SubscriberStorage
from net.util import ErrorKind
from utils.config_loader import retrieve_config
from utils.datatypes import UserReference, UserStatus
from utils.ds import BijectiveMap
if TYPE_CHECKING:
    from models import EveryoneEventChannel
else:
    from models import *  # noqa

import yaml  # type: ignore


@dataclass
class WebSocketWrapper:
    ws: WebSocket
    last_activity: int  # unixsecs of last user activity on the front-end (received with pings; cannot decrease or be less than last_message; activity usually assumes mouse movement)
    last_message: int  # unixsecs of any last message got from this socket (including pings and invalid messages)
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

    async def send_pong(self) -> None:
        await self.ws.send_text("pong")

    async def send_error(self, error: ErrorKind, details: Any) -> None:
        await self.ws.send_json(dict(
            error=error.value,
            details=details
        ))

    async def send_validation_error(self, error: ValidationError) -> None:
        await self.send_error(ErrorKind.VALIDATION_ERROR, error.errors())

    def get_status(self) -> UserStatus:
        now_ts = int(time.time())
        if now_ts - self.last_message > 60:  # 1 min
            return UserStatus.OFFLINE
        elif now_ts - self.last_activity > 300:  # 5 min
            return UserStatus.AWAY
        return UserStatus.ONLINE


@dataclass
class MutableState:
    shutdown_activated: bool = False  # TODO: Admin shutdown endpoint (Cancel all challenges; Broadcast announcement)
    token_to_user: BijectiveMap[str, UserReference] = BijectiveMap()
    ws_subscribers: SubscriberStorage = SubscriberStorage()
    last_guest_id: int = 0

    def add_guest(self, token: str) -> int:
        self.last_guest_id += 1
        self.token_to_user.add(token, UserReference.guest(self.last_guest_id))
        return self.last_guest_id

    def add_logged(self, token: str, login: str) -> None:
        self.token_to_user.add(token, UserReference.logged(login))

    def has_user_subscriber(self, user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self.ws_subscribers.has_user_subscriber(self.token_to_user, user_ref, channel)

    def get_user_status_in_channel(self, user_ref: UserReference, channel: EventChannel) -> UserStatus:
        return self.ws_subscribers.get_user_status_in_channel(self.token_to_user, user_ref, channel)


class App(FastAPI):
    @asynccontextmanager
    async def __lifespan(self: FastAPI):
        SQLModel.metadata.create_all(self.db_engine)  # All models were imported using wildcard at the top of this file
        with Session(self.db_engine) as session:
            ...  # TODO: Assign correct last_guest_id
        yield

    def __init__(self, rest_routers: list[APIRouter], ws_collections: list[WebSocketHandlerCollection]) -> None:
        super().__init__(lifespan=App.__lifespan)

        self.mutable_state: MutableState = MutableState()

        self.main_config: MainConfig = retrieve_config('main', MainConfig)
        self.secret_config: SecretConfig = retrieve_config('secret', SecretConfig)

        self.db_engine: Engine = create_engine(self.secret_config.db.url)

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
        now_ts = int(time.time())
        ws_wrapper = WebSocketWrapper(websocket, now_ts, now_ts)
        self.mutable_state.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while True:
                data = await websocket.receive_json()
                await self.ws_handlers.handle(self.mutable_state.token_to_user, ws_wrapper, data)
        except WebSocketDisconnect:
            self.mutable_state.ws_subscribers.fully_remove(ws_wrapper)
