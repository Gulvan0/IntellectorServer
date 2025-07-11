from fastapi import Request, Response
from routers import study, player, auth, other, challenge, game
from routers.websocket import game as ws_game
from net.fastapi_wrapper import App


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


@app.middleware("http")
async def middleware(request: Request, call_next):
    ...
    response: Response = await call_next(request)
    ...
    return response
