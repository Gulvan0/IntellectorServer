from src.auth import routes as auth_routes
from src.challenge import routes as challenge_routes
from src.game.routes import main as main_game_routes
from src.game.routes import external as external_game_routes
from src.player import routes as player_routes
from src.other import routes as other_routes
from src.study import routes as study_routes

from src.game.ws import handlers as ws_game

from src.net.core import App


app = App(
    rest_routers=[
        auth_routes.router,
        challenge_routes.router,
        main_game_routes.router,
        external_game_routes.router,
        player_routes.router,
        other_routes.router,
        study_routes.router,
    ],
    ws_collections=[
        ws_game.collection,
    ]
)
