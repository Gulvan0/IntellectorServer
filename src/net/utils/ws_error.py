from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pubsub.models.channel import EventChannel


class ErrorKind(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNKNOWN_EVENT = "unknown_event"
    AUTH_ERROR = "authorization_error"
    PROCESSING_ERROR = "processing_error"


@dataclass
class WebSocketException(Exception):
    message: str
    kind: ErrorKind = ErrorKind.PROCESSING_ERROR
    channel: "EventChannel | None" = None
    """Set when the error concerns a particular channel, so the client can tell which subscription failed"""
