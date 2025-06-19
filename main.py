from routers import study, player, auth, other, challenge, game
from routers.websocket import game as ws_game
from utils.fastapi_wrappers import App


app = App(
    rest_routers=[
        auth.router,
        challenge.router,
        game.router,
        player.router,
        study.router,
        other.router,
    ],
    ws_collections=[
        ws_game.collection,
    ]
)
