from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from models.log import WSLog
from models.other import WebsocketIncomingMessage
from net.util import ErrorKind, WebSocketException
from utils.datatypes import UserReference
from utils.ds import BijectiveMap

if TYPE_CHECKING:
    from net.fastapi_wrapper import WebSocketWrapper


type WebSocketIncomingEventHandlerCallable[T:BaseModel] = Callable[[WebSocketWrapper, UserReference | None, T], Coroutine[Any, Any, None]]


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

    async def handle(self, token_map: BijectiveMap[str, UserReference], ws: WebSocketWrapper, data: Any) -> None:
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
            with Session(ws.app.db_engine) as session:
                session.add(log_entry)
                session.commit()
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
                with Session(ws.app.db_engine) as session:
                    session.add(log_entry)
                    session.commit()
                await ws.send_error(ErrorKind.AUTH_ERROR, "Invalid token")
                return
            log_entry.authorized_as = client.reference
            with Session(ws.app.db_engine) as session:
                session.add(log_entry)
                session.commit()

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

    def generate_asyncapi_specification(self) -> dict[str, Any]:
        result: dict[str, dict[str, dict]] = dict(
            channels=dict(
                NO_CHANNEL=dict(
                    messages={}
                )
            ),
            operations=dict(
                receive=dict(
                    action="receive",
                    channel={
                        "$ref": "#/channels/NO_CHANNEL"
                    },
                    messages=[]
                )
            ),
            components=dict(
                messages={}
            )
        )
        for name, incoming_event in self._slug_to_handler.items():
            msg_ref = {"$ref": f"#/components/messages/{name}"}
            result["channels"]["NO_CHANNEL"]["messages"][name] = msg_ref
            result["operations"]["receive"]["messages"].append({
                "$ref": f"#/channels/NO_CHANNEL/messages/{name}"
            })

            payload_type: type[BaseModel] = incoming_event.payload_type
            msg_definition = dict(
                name=name,
                payload=payload_type.model_json_schema(ref_template=f'#/components/messages/{name}/payload/$defs/{{model}}')
            )
            if incoming_event.title:
                msg_definition["title"] = incoming_event.title
            if incoming_event.summary:
                msg_definition["summary"] = incoming_event.summary
            if incoming_event.description:
                msg_definition["description"] = incoming_event.description
            result["components"]["messages"][name] = msg_definition
        return result
