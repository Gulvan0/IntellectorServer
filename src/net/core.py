from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from jinja2 import Template
from pydantic import BaseModel, ValidationError
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import Engine, text

from src.common.user_ref import UserReference
from src.pubsub.models import EventChannel, EveryoneEventChannel
from src.config.models import MainConfig, SecretConfig
from src.log.models import ServerLaunch, WSLog
from src.net.incoming import WebSocketHandlerCollection
from src.net.outgoing import WebsocketOutgoingEvent, WebsocketOutgoingEventRegistry
from src.net.sub_storage import SubscriberStorage
from src.net.utils.ws_error import ErrorKind
from src.config.loader import load
from src.player.datatypes import UserStatus
from src.utils.bijective_map import BijectiveMap

from src.auth.models import *  # noqa: F401, F403
from src.challenge.models import *  # noqa: F401, F403
from src.common.models import *  # noqa: F401, F403
from src.config.models import *  # noqa: F401, F403
from src.game.models.chat import *  # noqa: F401, F403
from src.game.models.external import *  # noqa: F401, F403
from src.game.models.incoming_ws import *  # noqa: F401, F403
from src.game.models.main import *  # noqa: F401, F403
from src.game.models.offer import *  # noqa: F401, F403
from src.game.models.other import *  # noqa: F401, F403
from src.game.models.outcome import *  # noqa: F401, F403
from src.game.models.ply import *  # noqa: F401, F403
from src.game.models.rest import *  # noqa: F401, F403
from src.game.models.rollback import *  # noqa: F401, F403
from src.game.models.time_added import *  # noqa: F401, F403
from src.game.models.time_control import *  # noqa: F401, F403
from src.game.models.time_update import *  # noqa: F401, F403
from src.log.models import *  # noqa: F401, F403
from src.net.models import *  # noqa: F401, F403
from src.notification.models import *  # noqa: F401, F403
from src.other.models import *  # noqa: F401, F403
from src.player.models import *  # noqa: F401, F403
from src.pubsub.models import *  # noqa: F401, F403
from src.study.models import *  # noqa: F401, F403

import time
import json
import yaml  # type: ignore


LAST_GUEST_ID_QUERY_PATH = Path('resources/sql/last_guest_id.sql')


@dataclass
class WebSocketWrapper:
    app: App
    ws: WebSocket
    last_activity: int  # unixsecs of last user activity on the front-end (received with pings; cannot decrease or be less than last_message; activity usually assumes mouse movement)
    last_message: int  # unixsecs of any last message got from this socket (including pings and invalid messages)
    uuid: UUID = field(default_factory=uuid4)
    saved_token: str | None = None

    def __post_init__(self):
        self.send_json = self.ws.send_json

    def get_user_ref(self) -> str | None:
        if self.saved_token:
            user = self.app.mutable_state.token_to_user.get(self.saved_token)
            if user:
                return user.reference
        return None

    async def _send_logged_json(self, payload: dict) -> None:
        with Session(self.app.db_engine) as session:
            session.add(WSLog(
                connection_id=str(self.uuid),
                authorized_as=self.get_user_ref(),
                payload=json.dumps(payload, ensure_ascii=False),
                incoming=False
            ))
            session.commit()

        await self.ws.send_json(payload)

    async def send_event[T: BaseModel, C: EventChannel](self, event: WebsocketOutgoingEvent[T, C], payload: T, channel: C) -> None:
        await self._send_logged_json(dict(
            event=event.event_name,
            channel=channel.model_dump() if channel else None,
            body=payload.model_dump()
        ))

    async def send_pong(self) -> None:
        await self.ws.send_text("pong")

    async def send_error(self, error: ErrorKind, details: Any) -> None:
        await self._send_logged_json(dict(
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
    shutdown_activated: bool = False
    token_to_user: BijectiveMap[str, UserReference] = field(default_factory=BijectiveMap)
    ws_subscribers: SubscriberStorage = field(default_factory=SubscriberStorage)
    last_guest_id: int = 0
    game_timeout_not_earlier_than: dict[int, float] = field(default_factory=dict)

    def add_guest(self, token: str) -> int:
        self.last_guest_id += 1
        self.token_to_user.add(token, UserReference.guest(self.last_guest_id))
        return self.last_guest_id

    def add_logged(self, token: str, login: str) -> None:
        self.token_to_user.add(token, UserReference.logged(login))  # TODO: Update case

    def has_user_subscriber(self, user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self.ws_subscribers.has_user_subscriber(self.token_to_user, user_ref, channel)

    def get_user_status_in_channel(self, user_ref: UserReference, channel: EventChannel) -> UserStatus:
        return self.ws_subscribers.get_user_status_in_channel(self.token_to_user, user_ref, channel)


class App(FastAPI):
    @asynccontextmanager
    async def __lifespan(self: App):
        SQLModel.metadata.create_all(self.db_engine)  # All models were imported using wildcard at the top of this file

        last_guest_id_query = LAST_GUEST_ID_QUERY_PATH.read_text()
        with Session(self.db_engine) as session:
            session.add(ServerLaunch())
            self.mutable_state.last_guest_id = session.connection().execute(text(last_guest_id_query)).scalar() or 0
            session.commit()

        yield

    def __init__(self, rest_routers: list[APIRouter], ws_collections: list[WebSocketHandlerCollection]) -> None:
        super().__init__(lifespan=App.__lifespan)

        self.mutable_state: MutableState = MutableState()

        self.main_config: MainConfig = load('main', MainConfig)
        self.secret_config: SecretConfig = load('secret', SecretConfig)

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
        ws_wrapper = WebSocketWrapper(self, websocket, now_ts, now_ts)
        self.mutable_state.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while True:
                data = await websocket.receive_json()
                await self.ws_handlers.handle(self.mutable_state.token_to_user, ws_wrapper, data)
        except WebSocketDisconnect:
            self.mutable_state.ws_subscribers.fully_remove(ws_wrapper)
