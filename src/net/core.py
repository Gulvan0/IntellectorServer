from __future__ import annotations

from asyncio import TimerHandle
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from websockets import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from src.challenge.methods.update import cancel_public_challenges_by_caller
from src.common.user_ref import UserReference
from src.pubsub.models.channel import EventChannel, EveryoneEventChannel
from src.config.models import MainConfig, SecretConfig
from src.log.models import ServerLaunch, WSLog
from src.net.incoming import WebSocketHandlerCollection
from src.net.sub_storage import SubscriberStorage
from src.net.utils.ws_error import ErrorKind
from src.config.loader import load
from src.player.datatypes import UserStatus
from src.pubsub.outgoing_event.base import OutgoingEvent
from src.utils.bijective_map import BijectiveMap
from src.utils.async_orm_session import AsyncSession

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
from src.game.models.polymorphous import *  # noqa: F401, F403
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
from src.pubsub.models.channel import *  # noqa: F401, F403
from src.pubsub.models.other import *  # noqa: F401, F403
from src.pubsub.models.state import *  # noqa: F401, F403
from src.study.models import *  # noqa: F401, F403

import time
import json


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

    def get_user_ref(self) -> UserReference | None:
        if self.saved_token:
            return self.app.mutable_state.token_to_user.get(self.saved_token)
        return None

    async def _send_logged_json(self, payload: dict) -> None:
        async with AsyncSession(self.app.db_engine) as session:
            session.add(WSLog(
                connection_id=str(self.uuid),
                authorized_as=self.get_user_ref().reference,
                payload=json.dumps(payload, ensure_ascii=False),
                incoming=False
            ))
            await session.commit()

        await self.ws.send_json(payload)

    async def send_event[T: BaseModel | None, C: EventChannel | None](self, event_instance: OutgoingEvent[T, C]) -> None:
        await self._send_logged_json(event_instance.to_dict())

    async def send_pong(self) -> None:
        await self.ws.send_text("pong")

    async def send_unsubscribed(self) -> None:
        await self.ws.send_text("unsubscribed")

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
    game_timeout_check_timers: dict[int, TimerHandle] = field(default_factory=dict)
    user_challenge_cancelling_timers: dict[UserReference, TimerHandle] = field(default_factory=dict)

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
    async def __lifespan(self):
        SQLModel.metadata.create_all(self.db_engine)  # All models were imported using wildcard at the top of this file

        last_guest_id_query = LAST_GUEST_ID_QUERY_PATH.read_text()
        async with AsyncSession(self.db_engine) as session:
            result = session.exec_raw(last_guest_id_query)
            self.mutable_state.last_guest_id = result.scalar() or 0

            session.add(ServerLaunch())
            await session.commit()

        yield

    @asynccontextmanager
    async def get_db_session(self):
        async with AsyncSession(self.db_engine) as session:
            yield session

    def __init__(self, rest_routers: list[APIRouter], ws_collections: list[WebSocketHandlerCollection]) -> None:
        super().__init__(lifespan=App.__lifespan)

        self.mutable_state: MutableState = MutableState()

        self.main_config: MainConfig = load('main', MainConfig)
        self.secret_config: SecretConfig = load('secret', SecretConfig)

        self.db_engine: AsyncEngine = create_async_engine(self.secret_config.db.url)

        for router in rest_routers:
            self.include_router(router)

        self.ws_handlers: WebSocketHandlerCollection = WebSocketHandlerCollection.union(ws_collections)

        # self.regenerate_asyncapi_docs()  # TODO: Write v2 implementation and delegate to a separate module

        self.add_api_route("/ws_docs", self.websocket_docs_endpoint, response_class=HTMLResponse)
        self.add_websocket_route("/ws", self.websocket_endpoint)

    async def websocket_docs_endpoint(self):
        return HTMLResponse(content=Path('./resources/ws_api_docs/docs_page.html').read_text())

    async def __delay_challenge_cancellation(self, caller: UserReference):
        existing_timer_handle = self.mutable_state.user_challenge_cancelling_timers.get(caller)
        if existing_timer_handle:
            existing_timer_handle.cancel()

        loop = asyncio.get_running_loop()

        async def task():
            self.mutable_state.user_challenge_cancelling_timers.pop(caller, None)

            async with self.get_db_session() as session:
                return await cancel_public_challenges_by_caller(caller, session, self.mutable_state, self.secret_config)

        self.mutable_state.user_challenge_cancelling_timers[caller] = loop.call_later(60, lambda: asyncio.create_task(task()))

    async def websocket_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        now_ts = int(time.time())
        ws_wrapper = WebSocketWrapper(self, websocket, now_ts, now_ts)
        self.mutable_state.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while True:
                data = await websocket.receive_json()
                await self.ws_handlers.handle(self.mutable_state.token_to_user, ws_wrapper, data)
        except (WebSocketDisconnect, ConnectionClosedError, ConnectionClosed, ConnectionClosedOK):
            self.mutable_state.ws_subscribers.fully_remove(ws_wrapper)

            user = ws_wrapper.get_user_ref()
            challenge_channel = IncomingChallengesEventChannel(user.reference)  # noqa: F405
            if user and not self.mutable_state.ws_subscribers.count_subscribers(challenge_channel):
                await self.__delay_challenge_cancellation(user)
