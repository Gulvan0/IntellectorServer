from auth import routes as auth_routes
from challenge import routes as challenge_routes
from game.routes import main as main_game_routes
from game.routes import external as external_game_routes
from game.routes import internal as internal_game_routes
from player import routes as player_routes
from other import routes as other_routes
from study import routes as study_routes

from pubsub import ws_handlers as ws_pubsub

from net.core import App

from uvicorn import run


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
    ws_collections=[
        ws_pubsub.collection,
    ]
)


ssl_config = app.secret_config.ssl
run(
    "main:app",
    ssl_keyfile=ssl_config.key_path if ssl_config else None,
    ssl_certfile=ssl_config.cert_path if ssl_config else None
)
