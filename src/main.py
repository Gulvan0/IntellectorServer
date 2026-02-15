import asyncio
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

from uvicorn import Config, Server


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


async def run_server() -> None:
    ssl_config = app.secret_config.ssl
    config = Config(
        app,
        host="0.0.0.0",
        ssl_keyfile=ssl_config.key_path if ssl_config else None,
        ssl_certfile=ssl_config.cert_path if ssl_config else None
    )
    server = Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(run_server())
