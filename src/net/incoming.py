from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, ValidationError

from common.user_ref import UserReference
from log.models import WSLog
from net.models import WebsocketIncomingMessage
from net.utils.ws_error import ErrorKind, WebSocketException
from utils.bijective_map import BijectiveMap

import json
import time
import net.core as core


type WebSocketIncomingEventHandlerCallable[T:BaseModel] = Callable[
    [
        core.WebSocketWrapper,
        UserReference | None,
        T
    ],
    Coroutine[Any, Any, None]
]


@dataclass
class WebSocketIncomingEventHandler[T:BaseModel]:
    payload_type: type[T]
    handler_callable: WebSocketIncomingEventHandlerCallable[T]
    title: str | None
    summary: str | None
    description: str | None


@dataclass
class WebSocketHandlerCollection:
    _slug_to_handler: dict[str, WebSocketIncomingEventHandler] = field(default_factory=dict)

    @classmethod
    def union(cls, collections: list[WebSocketHandlerCollection]) -> WebSocketHandlerCollection:
        return WebSocketHandlerCollection({
            slug: handler
            for collection in collections
            for slug, handler in collection._slug_to_handler.items()
        })

    def register[T:BaseModel](
        self,
        payload_type: type[T],
        *,
        slug: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        description: str | None = None
    ):
        def decorator(handler_callable: WebSocketIncomingEventHandlerCallable[T]) -> WebSocketIncomingEventHandlerCallable[T]:
            actual_slug = slug or handler_callable.__name__
            assert actual_slug not in self._slug_to_handler
            self._slug_to_handler[actual_slug] = WebSocketIncomingEventHandler(payload_type, handler_callable, title, summary, description)
            return handler_callable
        return decorator

    async def handle(self, token_map: BijectiveMap[str, UserReference], ws: core.WebSocketWrapper, data: Any) -> None:
        now_ts = int(time.time())
        ws.last_message = now_ts

        try:
            payload = json.dumps(data, ensure_ascii=False)[:1000]
        except Exception:
            try:
                payload = str(data)[:1000]
            except Exception:
                payload = "unparsable"

        log_entry = WSLog(
            connection_id=str(ws.uuid),
            authorized_as=None,
            payload=payload,
            incoming=True
        )

        try:
            message = WebsocketIncomingMessage.model_validate(data)
        except ValidationError as e:
            async with ws.app.get_db_session() as session:
                session.add(log_entry)
                await session.commit()
            await ws.send_validation_error(e)
            return

        if message.event == "ping":
            last_activity_ts = message.body.get("last_activity")
            if last_activity_ts and isinstance(last_activity_ts, int):
                ws.last_activity = min(max(ws.last_activity, last_activity_ts), now_ts)
            await ws.send_pong()
            return

        ws.last_activity = now_ts

        if message.token:
            client = token_map.get(message.token)
            if not client:
                async with ws.app.get_db_session() as session:
                    session.add(log_entry)
                    await session.commit()
                await ws.send_error(ErrorKind.AUTH_ERROR, "Invalid token")
                return
            log_entry.authorized_as = client.reference
            async with ws.app.get_db_session() as session:
                session.add(log_entry)
                await session.commit()

        handler = self._slug_to_handler.get(message.event)
        if not handler:
            await ws.send_error(ErrorKind.UNKNOWN_EVENT, f"Event not found: {message.event}")
            return
        else:
            client = None

        try:
            payload = handler.payload_type.model_validate(message.body)
        except ValidationError as e:
            await ws.send_validation_error(e)
            return

        try:
            await handler.handler_callable(ws, client, payload)
        except WebSocketException as e:
            await ws.send_error(e.kind, e.message)
