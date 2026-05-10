import json

from fastapi.datastructures import Headers


MAX_BYTES = 65500


def __decode_long(long_bytes: bytes) -> str:
    return "CUT" + long_bytes[:MAX_BYTES].decode(errors="ignore")


def dump_headers(headers: Headers) -> str:
    try:
        dumped = json.dumps(dict(headers.items()), ensure_ascii=False)
        as_bytes = dumped.encode()
        if len(as_bytes) > MAX_BYTES:
            return __decode_long(as_bytes)
        else:
            return dumped
    except Exception:
        return "unparsable"


def dump_request_body(body: bytes) -> str:
    try:
        if not body:
            return "missing"
        elif len(body) > MAX_BYTES:
            return __decode_long(body)
        else:
            return body.decode()
    except Exception:
        return "unparsable"


def dump_response_body(body: bytes) -> str:
    if len(body) > MAX_BYTES:
        return __decode_long(body)
    else:
        try:
            return body.decode()
        except Exception:
            return "unparsable"
