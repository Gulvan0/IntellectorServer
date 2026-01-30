from dataclasses import dataclass
from typing import Callable
from fastapi import Response
from pydantic import BaseModel


@dataclass
class EarlyResponse(Exception):
    status_code: int
    body: BaseModel


def supports_early_responses(has_response_arg: bool = False) -> Callable:  # type: ignore[type-arg]
    def decorator(endpoint: Callable) -> Callable:  # type: ignore[type-arg]
        def wrapper(*, response: Response, **additional_kwargs):  # type: ignore
            try:
                return endpoint(response=response, **additional_kwargs) if has_response_arg else endpoint(**additional_kwargs)
            except EarlyResponse as early_resp:
                response.status_code = early_resp.status_code
                return early_resp.body
        return wrapper
    return decorator
