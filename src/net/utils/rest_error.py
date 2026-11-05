from enum import StrEnum, auto
from math import ceil
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class RestErrorCode(StrEnum):
    USER_NOT_FOUND = auto()
    INVALID_CREDENTIALS = auto()
    USER_ALREADY_EXISTS = auto()
    CALLEE_NOT_FOUND = auto()
    CHALLENGE_ALREADY_EXISTS = auto()
    TOO_MANY_ACTIVE_CHALLENGES = auto()  # extra fields: max_active_challenges
    TOO_MANY_DIRECT_CHALLENGES = auto()  # extra fields: max_active_challenges
    SERVER_RESTARTING = auto()
    RATE_LIMITED = auto()  # extra fields: retry_after_secs
    PAYLOAD_TOO_LARGE = auto()  # extra fields: max_bytes
    CHAT_RESTRICTED = auto()


STATUS_CODES: dict[RestErrorCode, int] = {
    RestErrorCode.USER_NOT_FOUND: 404,
    RestErrorCode.INVALID_CREDENTIALS: 401,
    RestErrorCode.USER_ALREADY_EXISTS: 422,
    RestErrorCode.CALLEE_NOT_FOUND: 404,
    RestErrorCode.CHALLENGE_ALREADY_EXISTS: 422,
    RestErrorCode.TOO_MANY_ACTIVE_CHALLENGES: 422,
    RestErrorCode.TOO_MANY_DIRECT_CHALLENGES: 422,
    RestErrorCode.SERVER_RESTARTING: 503,
    RestErrorCode.RATE_LIMITED: 429,
    RestErrorCode.PAYLOAD_TOO_LARGE: 413,
    RestErrorCode.CHAT_RESTRICTED: 403,
}


class RestException(HTTPException):
    """
    An HTTP error the client can tell apart by its machine-readable `code`.
    The response body is `{"detail": ..., "code": ..., **extra_fields}`.
    """

    def __init__(self, code: RestErrorCode, detail: str, **extra_fields: int | str | None) -> None:
        super().__init__(status_code=STATUS_CODES[code], detail=detail)
        self.code = code
        self.extra_fields = extra_fields

    def body(self) -> dict[str, Any]:
        return {"detail": self.detail, "code": self.code, **self.extra_fields}


def rate_limited_error(retry_after_secs: float) -> RestException:
    whole_secs = ceil(retry_after_secs)
    error = RestException(RestErrorCode.RATE_LIMITED, "Too many requests", retry_after_secs=whole_secs)
    error.headers = {"Retry-After": str(whole_secs)}
    return error


def payload_too_large_error(max_bytes: int) -> RestException:
    return RestException(RestErrorCode.PAYLOAD_TOO_LARGE, "Request body too large", max_bytes=max_bytes)


async def handle_rest_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RestException)
    return JSONResponse(content=exc.body(), status_code=exc.status_code, headers=exc.headers)
