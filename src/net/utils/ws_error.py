from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorKind(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNKNOWN_EVENT = "unknown_event"
    AUTH_ERROR = "authorization_error"
    PROCESSING_ERROR = "processing_error"


@dataclass(frozen=True)
class WebSocketException(Exception):
    message: str
    kind: ErrorKind = ErrorKind.PROCESSING_ERROR
