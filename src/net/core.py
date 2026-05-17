import traceback

from auth.models import *  # noqa: F401, F403
from challenge.methods.cancel import cancel_old_challenges
from challenge.models import *  # noqa: F401, F403
from common.models import *  # noqa: F401, F403
from config.models import *  # noqa: F401, F403
from game.models.chat import *  # noqa: F401, F403
from game.models.rest.external import *  # noqa: F401, F403
from game.models.rest.internal import *  # noqa: F401, F403
from game.models.main import *  # noqa: F401, F403
from game.models.offer import *  # noqa: F401, F403
from game.models.other import *  # noqa: F401, F403
from game.models.outcome import *  # noqa: F401, F403
from game.models.ply import *  # noqa: F401, F403
from game.models.polymorphous import *  # noqa: F401, F403
from game.models.rest.common import *  # noqa: F401, F403
from game.models.rollback import *  # noqa: F401, F403
from game.models.time_added import *  # noqa: F401, F403
from game.models.time_control import *  # noqa: F401, F403
from game.models.time_update import *  # noqa: F401, F403
from log.models import *  # noqa: F401, F403
from net.models import *  # type: ignore[no-redef]  # noqa: F401, F403
from notification.models import *  # noqa: F401, F403
from other.models import *  # noqa: F401, F403
from player.models import *  # noqa: F401, F403
from pubsub.models.channel import *  # type: ignore[no-redef]  # noqa: F401, F403
from pubsub.models.other import *  # noqa: F401, F403
from pubsub.models.state import *  # noqa: F401, F403
from study.models import *  # noqa: F401, F403

from board.opening import OpeningMapping, generate_mapping

from asyncio import Lock, TimerHandle
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from websockets import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from typing import TYPE_CHECKING
from common.user_ref import UserReference
from pubsub.models.channel import EventChannel, EveryoneEventChannel
from config.models import MainConfig, SecretConfig
from log.models import ServerLaunch, TaskFailureLog
from net.sub_storage import SubscriberStorage
from config.loader import load
from common.models import UserActivity
from utils.bijective_map import BijectiveMap
from utils.async_orm_session import AsyncSession
from net.ws_wrapper import WebSocketWrapper
from net.task_storage import ConcurrentTaskStorage

import time


if TYPE_CHECKING:
    from net.incoming import WebSocketHandlerCollection


LAST_GUEST_ID_QUERY_PATH = Path('resources/sql/last_guest_id.sql')


@dataclass
class MutableState:
    shutdown_activated: bool = False
    token_to_user: BijectiveMap[str, UserReference] = field(default_factory=BijectiveMap)
    ws_subscribers: SubscriberStorage = field(default_factory=SubscriberStorage)
    last_guest_id: int = 0
    game_timeout_check_timers: dict[int, TimerHandle] = field(default_factory=dict)
    user_challenge_cancelling_timers: dict[UserReference, TimerHandle] = field(default_factory=dict)
    concurrent_tasks: ConcurrentTaskStorage = field(default_factory=ConcurrentTaskStorage)

    __game_end_locks: dict[int, Lock] = field(default_factory=dict)

    def get_game_end_lock(self, game_id: int) -> Lock:
        return self.__game_end_locks.setdefault(game_id, Lock())

    def release_game_end_lock(self, game_id: int) -> None:
        self.__game_end_locks.pop(game_id, None)

    def add_guest(self, token: str) -> int:
        self.last_guest_id += 1
        self.token_to_user.update(token, UserReference.guest(self.last_guest_id))
        return self.last_guest_id

    def add_logged(self, token: str, login: str) -> None:
        user = UserReference.logged(login)
        self.token_to_user.update(token, user)

    def has_user_subscriber(self, user_ref: UserReference, channel: EventChannel = EveryoneEventChannel()) -> bool:
        return self.ws_subscribers.has_user_subscriber(self.token_to_user, user_ref, channel)

    def get_user_activity_in_channel(self, user_ref: UserReference, channel: EventChannel) -> UserActivity | None:
        return self.ws_subscribers.get_user_activity_in_channel(self.token_to_user, user_ref, channel)


class App(FastAPI):
    @asynccontextmanager
    async def __lifespan(self) -> AsyncGenerator[None, None]:
        async with self.db_engine.begin() as connection:
            # All models were imported using wildcard at the top of this file
            await connection.run_sync(SQLModel.metadata.create_all)

        last_guest_id_query = LAST_GUEST_ID_QUERY_PATH.read_text()
        async with AsyncSession(self.db_engine) as session:
            result = await session.exec_raw(last_guest_id_query)
            self.mutable_state.last_guest_id = result.scalar() or 0

            session.add(ServerLaunch())
            await session.commit()

        asyncio.create_task(self.stale_challenge_cancelation_loop())

        yield

    async def stale_challenge_cancelation_loop(self) -> None:
        while True:
            await asyncio.sleep(1800)  # repeat every 30 min
            try:
                async with self.get_db_session() as session:
                    await cancel_old_challenges(session, self.mutable_state, self.secret_config)
            except Exception:
                await self._log_task_failure("stale_challenge_cancelation")

    @asynccontextmanager
    async def get_db_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(self.db_engine) as session:
            yield session

    async def _log_task_failure(self, task_name: str, error: str | None = None) -> None:
        async with self.get_db_session() as session:
            session.add(TaskFailureLog(
                task=task_name,
                error=error or traceback.format_exc()
            ))
            await session.commit()

    def __init__(self, rest_routers: list[APIRouter], ws_collection: WebSocketHandlerCollection) -> None:
        super().__init__(lifespan=App.__lifespan)

        self.mutable_state: MutableState = MutableState()
        self.mutable_state.concurrent_tasks.on_failure = self._log_task_failure

        self.main_config: MainConfig = load('main', MainConfig)
        self.secret_config: SecretConfig = load('secret', SecretConfig)
        self.openings: OpeningMapping = generate_mapping()

        self.db_engine: AsyncEngine = create_async_engine(self.secret_config.db.url)

        for router in rest_routers:
            self.include_router(router)

        self.ws_handlers: WebSocketHandlerCollection = ws_collection

        # self.regenerate_asyncapi_docs()  # TODO: Write v2 implementation and delegate to a separate module

        self.add_api_route("/ws_docs", self.websocket_docs_endpoint, response_class=HTMLResponse)
        self.add_websocket_route("/ws", self.websocket_endpoint)

    async def websocket_docs_endpoint(self) -> HTMLResponse:
        return HTMLResponse(content=Path('./resources/ws_api_docs/docs_page.html').read_text())

    async def __plan_challenge_cancellation(self, caller: UserReference) -> None:
        from challenge.methods.cancel import cancel_public_challenges_by_caller

        existing_timer_handle = self.mutable_state.user_challenge_cancelling_timers.get(caller)
        if existing_timer_handle:
            return

        loop = asyncio.get_running_loop()

        async def task() -> None:
            self.mutable_state.user_challenge_cancelling_timers.pop(caller, None)

            challenge_channel = OutgoingChallengesEventChannel(user_ref=caller.reference)  # noqa: F405

            async with self.get_db_session() as session:
                if not self.mutable_state.ws_subscribers.count_subscribers(challenge_channel):
                    await cancel_public_challenges_by_caller(caller, session, self.mutable_state, self.secret_config)

        self.mutable_state.user_challenge_cancelling_timers[caller] = loop.call_later(60, lambda: self.mutable_state.concurrent_tasks.plan(task()))

    async def plan_challenge_cancellation_if_unwatched(self, user: UserReference | None) -> None:
        if not user:
            return

        challenge_channel = OutgoingChallengesEventChannel(user_ref=user.reference)  # noqa: F405
        if not self.mutable_state.ws_subscribers.count_subscribers(challenge_channel):
            await self.__plan_challenge_cancellation(user)

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        now_ts = int(time.time())
        ws_wrapper = WebSocketWrapper(self, websocket, now_ts, now_ts)
        self.mutable_state.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                except asyncio.TimeoutError:
                    if time.time() - ws_wrapper.last_message > 60:
                        raise WebSocketDisconnect()
                else:
                    await self.ws_handlers.handle(self.mutable_state.token_to_user, ws_wrapper, data)
        except (WebSocketDisconnect, ConnectionClosedError, ConnectionClosed, ConnectionClosedOK):
            self.mutable_state.ws_subscribers.fully_remove(ws_wrapper)

            await self.plan_challenge_cancellation_if_unwatched(ws_wrapper.get_user_ref())
