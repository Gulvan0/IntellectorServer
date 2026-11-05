import traceback

from auth.models import *  # noqa: F401, F403
from challenge.methods.cancel import cancel_old_challenges
from game.methods.presence import replan_all_presence_checks
from game.methods.timeout import replan_all_timeout_checks
from player.status import publish_player_status_changes
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
from game.models.presence import *  # noqa: F401, F403
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

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, TYPE_CHECKING
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from other.api_version import API_MISMATCH_CLOSE_CODE, API_VERSION
from websockets import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from common.user_ref import UserReference
from pubsub.models.channel import EveryoneEventChannel
from pubsub.ws_handlers import broadcast_subscriber_left
from config.models import MainConfig, SecretConfig
from log.models import ServerLaunch, TaskFailureLog
from log.ws_log_buffer import WSLogBuffer
from config.loader import load
from utils.async_orm_session import AsyncSession
from net.ws_wrapper import WebSocketWrapper
from net.rate_limit import RateLimiter, RateLimitGroup, client_host
from net.state import MutableState
from net.utils.rest_error import RestException, handle_rest_exception

import time


if TYPE_CHECKING:
    from net.incoming import WebSocketHandlerCollection


LAST_GUEST_ID_QUERY_PATH = Path('resources/sql/last_guest_id.sql')
GOING_AWAY_CLOSE_CODE = 1001
INVALID_PAYLOAD_CLOSE_CODE = 1007
RATE_LIMITED_CLOSE_CODE = 4429


class App(FastAPI):
    @asynccontextmanager
    async def __lifespan(self) -> AsyncGenerator[None, None]:
        # The schema belongs to Alembic: nothing is created here
        last_guest_id_query = LAST_GUEST_ID_QUERY_PATH.read_text()
        async with AsyncSession(self.db_engine) as session:
            result = await session.exec_raw(last_guest_id_query)
            self.mutable_state.last_guest_id = result.scalar() or 0

            session.add(ServerLaunch())
            await session.commit()

            await replan_all_timeout_checks(session, self.mutable_state, self.main_config, self.secret_config)
            await replan_all_presence_checks(session, self.mutable_state, self.main_config, self.secret_config)

        background_tasks = [
            asyncio.create_task(self.stale_challenge_cancelation_loop()),
            asyncio.create_task(self.player_status_publication_loop()),
            asyncio.create_task(self.ws_log_flush_loop()),
        ]

        yield

        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        await self.ws_log_buffer.flush()
        await self.db_engine.dispose()  # or the pooled connections are closed by their finalizers, after the event loop is gone

    async def stale_challenge_cancelation_loop(self) -> None:
        while True:
            await asyncio.sleep(1800)  # repeat every 30 min
            try:
                async with self.get_db_session() as session:
                    await cancel_old_challenges(session, self.mutable_state, self.secret_config)
            except Exception:
                await self.log_caught_failure("stale_challenge_cancelation")

    async def player_status_publication_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            try:
                async with self.get_db_session() as session:
                    await publish_player_status_changes(session, self.mutable_state)
            except Exception:
                await self.log_caught_failure("player_status_publication")

    async def ws_log_flush_loop(self) -> None:
        while True:
            await self.ws_log_buffer.wait_until_flush_due()
            try:
                await self.ws_log_buffer.flush()
            except Exception:
                await self.log_caught_failure("ws_log_flush")

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

    async def log_caught_failure(self, task_name: str) -> None:
        """To call from an except block of code that has to outlive a DB outage: there the failure can't be stored, and that mustn't end it"""
        error = traceback.format_exc()
        try:
            await self._log_task_failure(task_name, error)
        except Exception:
            print(error)

    def __init__(self, rest_routers: list[APIRouter], ws_collection: WebSocketHandlerCollection) -> None:
        super().__init__(lifespan=App.__lifespan)

        self.mutable_state: MutableState = MutableState()
        self.mutable_state.concurrent_tasks.on_failure = self._log_task_failure

        self.main_config: MainConfig = load('main', MainConfig)
        self.secret_config: SecretConfig = load('secret', SecretConfig)
        self.rate_limiter: RateLimiter = RateLimiter(self.main_config.rate_limits)
        self.openings: OpeningMapping = generate_mapping()

        self.db_engine: AsyncEngine = create_async_engine(
            self.secret_config.db.url,
            pool_size=self.main_config.limits.db_pool_size,
            max_overflow=self.main_config.limits.db_pool_max_overflow,
            pool_pre_ping=True  # a MySQL restart would otherwise leave dead connections in the pool
        )
        self.mutable_state.concurrent_tasks.db_engine = self.db_engine
        self.ws_log_buffer: WSLogBuffer = WSLogBuffer(self.db_engine)

        for router in rest_routers:
            self.include_router(router)

        self.add_exception_handler(RestException, handle_rest_exception)

        self.ws_handlers: WebSocketHandlerCollection = ws_collection

        self.add_api_route("/ws_docs", self.websocket_docs_endpoint)
        self.add_websocket_route("/ws", self.websocket_endpoint)

    async def websocket_docs_endpoint(self) -> None:
        """Serves nothing: the WS docs aren't generated"""

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

    async def __save_last_ws_activity(self, login: str, last_activity: int) -> None:
        async with self.get_db_session() as session:
            db_player = await session.get(Player, login)
            if db_player and last_activity > db_player.last_ws_activity:
                db_player.last_ws_activity = last_activity
                session.add(db_player)
                await session.commit()

    async def __close_websocket(self, websocket: WebSocket, code: int) -> None:
        try:
            await asyncio.wait_for(websocket.close(code=code), self.main_config.keep_alive.send_timeout_secs)
        except Exception:
            pass  # stalled, or gone already

    async def close_all_connections(self) -> None:
        await asyncio.gather(*[
            self.__close_websocket(subscriber.ws.ws, GOING_AWAY_CLOSE_CODE)
            for subscriber in self.mutable_state.ws_subscribers.get_subscribers()
        ])

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        host = client_host(websocket.client)
        if self.rate_limiter.take(RateLimitGroup.WS_CONNECT, host) is not None or not self.rate_limiter.open_connection(host):
            await websocket.close()  # not accepted yet: the handshake fails, and the client retries with a delay
            return

        try:
            await self.__serve_websocket(websocket)
        finally:
            self.rate_limiter.close_connection(host)

    async def __serve_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        if websocket.query_params.get("api") != str(API_VERSION):
            await websocket.close(code=API_MISMATCH_CLOSE_CODE, reason=str(API_VERSION))
            return

        now_ts = int(time.time())
        ws_wrapper = WebSocketWrapper(self, websocket, now_ts, now_ts, endpoint_task=asyncio.current_task())
        self.mutable_state.ws_subscribers.subscribe(ws_wrapper, EveryoneEventChannel())
        try:
            while not ws_wrapper.dropped:
                ws_wrapper.awaiting_message = True
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=self.main_config.keep_alive.silence_check_interval_secs)
                except asyncio.TimeoutError:
                    if time.time() - ws_wrapper.last_message > self.main_config.keep_alive.max_client_silence_secs:
                        raise WebSocketDisconnect()
                except (ValueError, KeyError, TypeError):  # not JSON, or a binary frame: no client of ours sends these
                    await self.__close_websocket(websocket, INVALID_PAYLOAD_CLOSE_CODE)
                    break
                else:
                    ws_wrapper.awaiting_message = False
                    if self.rate_limiter.take(RateLimitGroup.WS_MESSAGE, str(ws_wrapper.uuid)) is not None:
                        await self.__close_websocket(websocket, RATE_LIMITED_CLOSE_CODE)
                        break
                    await self.ws_handlers.handle(ws_wrapper, data)
        except (WebSocketDisconnect, ConnectionClosedError, ConnectionClosed, ConnectionClosedOK):
            pass
        except asyncio.CancelledError:
            if not ws_wrapper.dropped:
                raise
            current_task = asyncio.current_task()
            assert current_task
            current_task.uncancel()
        finally:
            self.__forget_websocket(ws_wrapper)

    def __forget_websocket(self, ws_wrapper: WebSocketWrapper) -> None:
        """Whatever ended the connection. The rest is planned, so that a failure in one part neither stops the others nor goes unlogged"""
        ws_wrapper.close_outbox()
        client = ws_wrapper.get_user_ref()
        channels = self.mutable_state.ws_subscribers.get_subscriptions(ws_wrapper)
        self.mutable_state.ws_subscribers.fully_remove(ws_wrapper)

        tasks = self.mutable_state.concurrent_tasks
        if client and client.is_player():
            tasks.plan(self.__save_last_ws_activity(client.reference, ws_wrapper.last_activity))

        for channel in channels:
            if channel != EveryoneEventChannel():
                tasks.plan(broadcast_subscriber_left(ws_wrapper, client, channel))

        tasks.plan(self.plan_challenge_cancellation_if_unwatched(client))
