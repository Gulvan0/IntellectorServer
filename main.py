import json
from fastapi import Request, Response
from sqlmodel import Session
from models.log import RESTRequestLog, RESTResponseLog
from routers import study, player, auth, other, challenge, game
from routers.websocket import game as ws_game
from net.fastapi_wrapper import App
from utils.constants import USER_TOKEN_HEADER


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
    try:
        headers_json = json.dumps(dict(request.headers.items()), ensure_ascii=False)
    except Exception:
        headers_json = "unparsable"

    try:
        body = await request.body()
        decoded_body = body.decode() if body else "missing"
    except Exception:
        decoded_body = "unparsable"

    token = request.headers.get(USER_TOKEN_HEADER)
    authorized_as = app.mutable_state.token_to_user.get(token) if token else None

    with Session(app.db_engine) as session:
        request_entry = RESTRequestLog(
            client_host=request.client.host if request.client else "unknown",
            authorized_as=authorized_as,
            endpoint=request.url.path,
            method=request.method,
            headers_json=headers_json,
            payload=decoded_body,
        )
        session.add(request_entry)
        session.commit()
        request_id = request_entry.id

    response: Response = await call_next(request)

    if isinstance(response.body, bytes):
        try:
            decoded_response = response.body.decode()
        except Exception:
            decoded_response = "unparsable"
    else:
        decoded_response = "stream"

    with Session(app.db_engine) as session:
        response_entry = RESTResponseLog(
            request_id=request_id,
            response_code=response.status_code,
            response=decoded_response
        )
        session.add(response_entry)
        session.commit()

    return response
