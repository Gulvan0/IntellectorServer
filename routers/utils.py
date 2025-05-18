from dataclasses import dataclass
from typing import Callable
from fastapi import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlmodel import Session

from database import engine


def get_session():
    with Session(engine) as session:
        yield session


USER_TOKEN_HEADER_SCHEME = APIKeyHeader(name="intellector-user-token")
OPTIONAL_USER_TOKEN_HEADER_SCHEME = APIKeyHeader(name="intellector-user-token", auto_error=False)


@dataclass
class EarlyResponse(Exception):
    status_code: int
    body: BaseModel


def supports_early_responses(has_response_arg: bool = False):
    def decorator(endpoint: Callable):
        def wrapper(*, response: Response, **additional_kwargs):
            try:
                return endpoint(response=response, **additional_kwargs) if has_response_arg else endpoint(**additional_kwargs)
            except EarlyResponse as early_resp:
                response.status_code = early_resp.status_code
                return early_resp.body
        return wrapper
    return decorator
