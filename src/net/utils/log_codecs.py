import json
from typing import Any

from fastapi.datastructures import Headers

from common.constants import USER_TOKEN_HEADER


MAX_BYTES = 65500
KEPT_TOKEN_CHARS = 8
SECRET_HEADERS = {"authorization", "cookie"}


def __decode_long(long_bytes: bytes) -> str:
    return "CUT" + long_bytes[:MAX_BYTES].decode(errors="ignore")


def __truncate_str(raw: str) -> str:
    as_bytes = raw.encode()
    if len(as_bytes) > MAX_BYTES:
        return __decode_long(as_bytes)
    else:
        return raw


def __dump_json_dict(raw: dict) -> str:
    try:
        try:
            dumped = json.dumps(raw, ensure_ascii=False)
        except Exception:
            dumped = str(raw)
        return __truncate_str(dumped)
    except Exception:
        return "unparsable"


def redact_token(token: str) -> str:
    """Keeps just enough of a session token to join the logs on it"""
    return f"{token[:KEPT_TOKEN_CHARS]}***"


def __redact_header(name: str, value: str) -> str:
    if name == USER_TOKEN_HEADER:
        return redact_token(value)
    return "***" if name in SECRET_HEADERS else value


def dump_headers(headers: Headers) -> str:
    return __dump_json_dict({name: __redact_header(name, value) for name, value in headers.items()})


def dump_bytes(body: bytes) -> str:
    try:
        if not body:
            return "missing"
        elif len(body) > MAX_BYTES:
            return __decode_long(body)
        else:
            return body.decode()
    except Exception:
        return "unparsable"


def dump_ws_payload(data: Any) -> str:
    return __dump_json_dict(data)
