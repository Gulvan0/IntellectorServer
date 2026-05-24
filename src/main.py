import asyncio
from asyncio import StreamWriter
import logging
from ssl import SSLError

from auth import routes as auth_routes
from challenge import routes as challenge_routes
from game.routes import common as main_game_routes
from game.routes import external as external_game_routes
from game.routes import internal as internal_game_routes
from player import routes as player_routes
from other import routes as other_routes
from study import routes as study_routes

from pubsub import ws_handlers as ws_pubsub

from net.core import App
from net.catch_exceptions_middleware import CatchExceptionsMiddleware

from fastapi.middleware.cors import CORSMiddleware
from hypercorn.config import Config
from hypercorn.asyncio import serve


# Monkey patch for ignoring errors arising from race conditions introduced by Python3.14 Hypercorn
_original_wait_closed = StreamWriter.wait_closed


async def _patched_wait_closed(self: StreamWriter) -> None:
    try:
        await asyncio.wait_for(_original_wait_closed(self), timeout=5.0)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    except SSLError as e:
        if "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in str(e):
            pass  # Client sent data after SSL close — safe to ignore
        else:
            raise


StreamWriter.wait_closed = _patched_wait_closed  # type: ignore[method-assign]


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
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_server() -> None:
    logging.basicConfig(level=logging.INFO)

    config = Config()
    config.bind = ["0.0.0.0:8443"]
    config.accesslog = logging.getLogger("hypercorn.access")
    config.errorlog = logging.getLogger("hypercorn.error")
    config.keyfile = app.secret_config.ssl.key_path
    config.certfile = app.secret_config.ssl.cert_path
    await serve(app, config)  # type: ignore


if __name__ == "__main__":
    asyncio.run(run_server())
