from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from net.utils.rest_error import handle_rest_exception, payload_too_large_error


MESSAGE_TOO_BIG_CLOSE_CODE = 1009


class SizeLimitMiddleware:
    """Caps what a client can make the server hold in memory. Done here rather than in the ASGI server's settings, as not
    every server has them for HTTP bodies, and this way the caps stay in force whichever server runs the app"""

    def __init__(self, app: ASGIApp, max_http_body_bytes: int, max_ws_message_bytes: int) -> None:
        self.app = app
        self.max_http_body_bytes = max_http_body_bytes
        self.max_ws_message_bytes = max_ws_message_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self.__serve_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self.app(scope, self.__limit_ws_messages(receive, send), send)
        else:
            await self.app(scope, receive, send)

    async def __reject_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        response = await handle_rest_exception(request, payload_too_large_error(self.max_http_body_bytes))
        await response(scope, receive, send)

    def __declares_too_much(self, scope: Scope) -> bool:
        content_length = Request(scope).headers.get("content-length", "")
        return content_length.isdecimal() and int(content_length) > self.max_http_body_bytes

    async def __serve_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The body is read up front, as a chunked one doesn't declare its size, and a limit hit once the app is reading
        it could only be reported as a failure of the app"""
        if self.__declares_too_much(scope):
            await self.__reject_http(scope, receive, send)
            return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # the client is gone

            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_http_body_bytes:
                await self.__reject_http(scope, receive, send)
                return

            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body_delivered = False

        async def replay_body() -> Message:
            nonlocal body_delivered
            if body_delivered:
                return await receive()
            body_delivered = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay_body, send)

    def __limit_ws_messages(self, receive: Receive, send: Send) -> Receive:
        async def limited_receive() -> Message:
            message = await receive()
            if message["type"] != "websocket.receive":
                return message

            text = message.get("text")
            size = len(text.encode()) if text is not None else len(message.get("bytes") or b"")
            if size <= self.max_ws_message_bytes:
                return message

            await send({"type": "websocket.close", "code": MESSAGE_TOO_BIG_CLOSE_CODE, "reason": ""})
            return {"type": "websocket.disconnect", "code": MESSAGE_TOO_BIG_CLOSE_CODE}

        return limited_receive
