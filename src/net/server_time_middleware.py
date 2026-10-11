import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send


SERVER_TIME_HEADER = "X-Server-Time"


class ServerTimeMiddleware:
    """Stamps each HTTP response with the server's Unix time in milliseconds, for clients to estimate their clock offset."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_time(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((SERVER_TIME_HEADER.lower().encode(), str(round(time.time() * 1000)).encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_time)
