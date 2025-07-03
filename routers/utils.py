from dataclasses import dataclass
from typing import Callable
from fastapi import Depends, HTTPException, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlmodel import Session

from database import engine
from globalstate import GlobalState, UserReference
from models.player import PlayerRole
from utils.datatypes import UserRole


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


# Dependency Injectors


def get_mandatory_user(token: str = Depends(USER_TOKEN_HEADER_SCHEME)) -> UserReference:
    user = GlobalState.token_to_user.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_mandatory_player_login(token: str = Depends(USER_TOKEN_HEADER_SCHEME)) -> str:
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    return client.login


def get_mandatory_admin_login(session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME)) -> str:
    client_login = get_mandatory_player_login(token)

    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")

    return client_login


def get_optional_player_login(token: str | None = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME)) -> str | None:
    if token is not None:
        client = GlobalState.token_to_user.get(token)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not client.is_guest():
            return client.login
    return None
