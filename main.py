from routers import study, player, auth, other, challenge
from routers.websocket import game
from utils.fastapi_wrappers import App


app = App(
    rest_routers=[
        auth.router,
        challenge.router,
        player.router,
        study.router,
        other.router,
    ],
    ws_collections=[
        game.collection,
    ]
)
