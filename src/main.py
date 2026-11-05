import asyncio
import logging
import os
import signal
from contextlib import nullcontext
from types import FrameType
from typing import Any

from auth import routes as auth_routes
from challenge import routes as challenge_routes
from game.routes import common as main_game_routes
from game.routes import external as external_game_routes
from game.routes import internal as internal_game_routes
from player import routes as player_routes
from other import routes as other_routes
from study import routes as study_routes

from pubsub import ws_handlers as ws_pubsub

from config.stage import is_test_stage
from net.core import App
from net.catch_exceptions_middleware import CatchExceptionsMiddleware
from net.rate_limit_middleware import RateLimitMiddleware
from net.server_time_middleware import SERVER_TIME_HEADER, ServerTimeMiddleware
from net.size_limit_middleware import SizeLimitMiddleware

from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = App(
    rest_routers=[
        auth_routes.router,
        challenge_routes.router,
        external_game_routes.router,
        internal_game_routes.router,
        main_game_routes.router,
        player_routes.router,
        other_routes.router,
        study_routes.router,
    ],
    ws_collection=ws_pubsub.collection
)


app.add_middleware(CatchExceptionsMiddleware)
app.add_middleware(
    SizeLimitMiddleware,
    max_http_body_bytes=app.main_config.limits.max_http_body_bytes,
    max_ws_message_bytes=app.main_config.limits.max_ws_message_bytes,
)
app.add_middleware(RateLimitMiddleware, limiter=app.rate_limiter)
app.add_middleware(ServerTimeMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[SERVER_TIME_HEADER],
)


PROD_HOST = "127.0.0.1"
PROD_PORT = int(os.getenv("PORT", "8000"))  # the override is for rehearsals next to another service on 8000
TEST_TLS_PORT = 8443
TEST_PLAIN_HTTP_PORT = 8080
EXIT_GRACE_SECS = 10


class Server(uvicorn.Server):
    def capture_signals(self) -> Any:
        """Several servers share this process: their signal handlers would replace one another, so run_server installs one for all"""
        return nullcontext()


async def wait_until_exit_overdue() -> None:
    """The server can't finish exiting while a connection is open. A stalled one takes no close, so it gets a limited time"""
    await app.mutable_state.exit_event.wait()
    await app.close_all_connections()
    await asyncio.sleep(EXIT_GRACE_SECS)


async def stop_on_exit_event(servers: list[Server]) -> None:
    await app.mutable_state.exit_event.wait()
    for server in servers:
        server.should_exit = True


def create_servers() -> list[Server]:
    ws_max_size = app.main_config.limits.max_ws_message_bytes  # so that a bigger message isn't even buffered

    if not is_test_stage():
        # behind Caddy: the real client address comes from the forwarded headers, trusted from the loopback only
        config = uvicorn.Config(
            app,
            host=PROD_HOST,
            port=PROD_PORT,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
            access_log=False,  # every request is in the database log already
            ws_max_size=ws_max_size,
            log_config=None,
        )
        return [Server(config)]

    ssl_params = app.secret_config.ssl
    assert ssl_params is not None, "The test stage needs the ssl section of secret.yaml"
    tls_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=TEST_TLS_PORT,
        ssl_keyfile=ssl_params.key_path,
        ssl_certfile=ssl_params.cert_path,
        proxy_headers=False,
        ws_max_size=ws_max_size,
        log_config=None,
    )
    # for devices that cannot trust the self-signed certificate (e.g. a phone on the local network);
    # the TLS listener runs the app's startup and shutdown, so this one must not repeat them
    plain_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=TEST_PLAIN_HTTP_PORT,
        lifespan="off",
        proxy_headers=False,
        ws_max_size=ws_max_size,
        log_config=None,
    )
    return [Server(tls_config), Server(plain_config)]


def install_signal_handlers(servers: list[Server]) -> None:
    def handle(signum: int, frame: FrameType | None) -> None:
        for server in servers:
            if server.should_exit and signum == signal.SIGINT:
                server.force_exit = True
            server.should_exit = True

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)


async def run_server() -> None:
    logging.basicConfig(level=logging.INFO)

    servers = create_servers()
    install_signal_handlers(servers)

    serving: asyncio.Future[Any] = asyncio.ensure_future(asyncio.gather(*(server.serve() for server in servers)))
    stopper = asyncio.create_task(stop_on_exit_event(servers))
    exit_overdue = asyncio.create_task(wait_until_exit_overdue())
    await asyncio.wait([serving, exit_overdue], return_when=asyncio.FIRST_COMPLETED)
    stopper.cancel()

    if serving.done():
        exit_overdue.cancel()
        serving.result()
    else:
        logging.getLogger("uvicorn.error").warning("Connections are still open past the exit grace: stopping regardless")
        for server in servers:
            server.force_exit = True
        await asyncio.gather(serving, return_exceptions=True)
        await app.ws_log_buffer.flush()


if __name__ == "__main__":
    asyncio.run(run_server())
