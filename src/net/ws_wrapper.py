from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from fastapi import WebSocket
from pydantic import BaseModel, ValidationError
from typing import TYPE_CHECKING
from common.user_ref import UserReference
from pubsub.models.channel import EventChannel
from log.models import WSLog
from net.utils.ws_error import ErrorKind
from player.datatypes import UserStatus
from pubsub.outgoing_event.base import OutgoingEvent
from utils.async_orm_session import AsyncSession

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

    def __post_init__(self) -> None:
        self.send_json = self.ws.send_json

    def get_user_ref(self) -> UserReference | None:
        if self.saved_token:
            return self.app.mutable_state.token_to_user.get(self.saved_token)
        return None

    async def _send_logged_json(self, payload: dict[str, Any]) -> None:
        async with AsyncSession(self.app.db_engine) as session:
            user = self.get_user_ref()
            session.add(WSLog(
                connection_id=str(self.uuid),
                authorized_as=user.reference if user else None,
                payload=json.dumps(payload, ensure_ascii=False),
                incoming=False
            ))
            await session.commit()

        await self.ws.send_json(payload)

    async def send_event[T: BaseModel | None, C: EventChannel | None](self, event_instance: OutgoingEvent[T, C]) -> None:
        await self._send_logged_json(event_instance.to_dict())

    async def send_pong(self) -> None:
        await self.ws.send_text("pong")

    async def send_unsubscribed(self) -> None:
        await self.ws.send_text("unsubscribed")

    async def send_error(self, error: ErrorKind, details: Any) -> None:
        await self._send_logged_json(dict(
            error=error.value,
            details=details
        ))

    async def send_validation_error(self, error: ValidationError) -> None:
        await self.send_error(ErrorKind.VALIDATION_ERROR, error.errors())

    def get_status(self) -> UserStatus:
        now_ts = int(time.time())
        if now_ts - self.last_message > 60:  # 1 min
            return UserStatus.OFFLINE
        elif now_ts - self.last_activity > 300:  # 5 min
            return UserStatus.AWAY
        return UserStatus.ONLINE
