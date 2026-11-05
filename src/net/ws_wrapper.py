import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from fastapi import WebSocket
from pydantic import BaseModel, ValidationError
from typing import TYPE_CHECKING
from common.datatypes import UserStatus
from common.models import UserActivity
from common.user_ref import UserReference
from net.models import WebsocketWrapperDump
from net.utils.log_codecs import dump_ws_payload
from pubsub.models.channel import EventChannel
from log.models import WSLog
from net.utils.ws_error import ErrorKind
from pubsub.outgoing_event.base import OutgoingEvent

import time
import json


if TYPE_CHECKING:
    from net.core import App


@dataclass
class WebSocketWrapper:
    app: App
    ws: WebSocket
    last_activity: int  # unixsecs of last user activity on the front-end (received with pings; cannot decrease or be less than last_message; activity usually assumes mouse movement)
    last_message: int  # unixsecs of any last message got from this socket (including pings and invalid messages)
    uuid: UUID = field(default_factory=uuid4)
    saved_token: str | None = None
    endpoint_task: asyncio.Task[None] | None = None  # serves this connection; ending it unsubscribes the connection
    awaiting_message: bool = False  # the endpoint is idle: cancelling it interrupts no work
    dropped: bool = False
    _outbox: asyncio.Queue[dict[str, Any] | str] = field(default_factory=asyncio.Queue, init=False, repr=False)  # a str is a text frame, a dict is sent as JSON
    _outbox_closed: bool = field(default=False, init=False, repr=False)
    _writer_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.send_json = self.ws.send_json

    def dump(self, tags: list[str] = []) -> WebsocketWrapperDump:
        user_ref = self.get_user_ref()
        return WebsocketWrapperDump(
            last_activity=self.last_activity,
            last_message=self.last_message,
            activity=self.get_activity_data(),
            saved_token=self.saved_token,
            saved_user_ref=user_ref.reference if user_ref else None,
            tags=tags
        )

    def get_user_ref(self) -> UserReference | None:
        if self.saved_token:
            return self.app.mutable_state.token_to_user.get(self.saved_token)
        return None

    def _enqueue(self, frame: dict[str, Any] | str) -> None:
        """Everything the client gets goes through here, so that it gets it in the order of the calls"""
        if self.dropped or self._outbox_closed:
            return
        self._outbox.put_nowait(frame)
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(self._write_frames())

    async def _write_frames(self) -> None:
        """Writes the queued frames one by one. A connection that can't take one in time is dropped, so that
        its unsent events don't pile up on the server; a close can't be sent to it either, the client notices the silence itself"""
        timeout = self.app.main_config.keep_alive.send_timeout_secs
        while True:
            frame = await self._outbox.get()
            if self.dropped:
                continue

            try:
                if isinstance(frame, str):
                    await asyncio.wait_for(self.ws.send_text(frame), timeout)
                else:
                    user = self.get_user_ref()
                    self.app.ws_log_buffer.add(WSLog(
                        connection_id=str(self.uuid),
                        authorized_as=user.reference if user else None,
                        payload=dump_ws_payload(frame),
                        incoming=False
                    ))
                    await asyncio.wait_for(self.ws.send_json(frame), timeout)
            except TimeoutError:
                self.dropped = True
                if self.endpoint_task and self.awaiting_message:
                    self.endpoint_task.cancel()
            except Exception:
                self._outbox_closed = True  # the connection is gone; its endpoint notices and unsubscribes it
                return

    def close_outbox(self) -> None:
        """The connection is over: whatever is still queued is not going to be sent"""
        self._outbox_closed = True
        if self._writer_task is not None:
            self._writer_task.cancel()

    def send_event[T: BaseModel | None, C: EventChannel](self, event_instance: OutgoingEvent[T, C]) -> None:
        self._enqueue(event_instance.to_dict())

    def send_pong(self) -> None:
        self._enqueue("pong")

    def send_unsubscribed(self) -> None:
        self._enqueue("unsubscribed")

    def send_error(self, error: ErrorKind, details: Any, channel: EventChannel | None = None) -> None:
        payload = dict(
            error=error.value,
            details=details
        )
        if channel:
            payload["channel"] = channel.model_dump(mode="json")
        self._enqueue(payload)

    def send_validation_error(self, error: ValidationError) -> None:
        self.send_error(ErrorKind.VALIDATION_ERROR, error.errors())

    def get_activity_data(self) -> UserActivity:
        keep_alive = self.app.main_config.keep_alive
        now_ts = int(time.time())
        if now_ts - self.last_message > keep_alive.max_client_silence_secs:
            status = UserStatus.OFFLINE
        elif now_ts - self.last_activity > keep_alive.away_after_secs:
            status = UserStatus.AWAY
        else:
            status = UserStatus.ONLINE
        return UserActivity(status=status, last_active_unixsecs=self.last_activity)
