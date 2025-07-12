from dataclasses import dataclass
from typing import Annotated, Callable
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, StringConstraints
from sqlmodel import Session

from models.config import MainConfig, SecretConfig
from models.player import PlayerRole
from utils.constants import USER_TOKEN_HEADER
from utils.datatypes import UserReference, UserRole
from net.fastapi_wrapper import App, MutableState


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


PlayerLogin = Annotated[str, StringConstraints(to_lower=True)]


# Dependency Injectors


UserTokenHeaderDependency = Annotated[str, Depends(APIKeyHeader(name=USER_TOKEN_HEADER))]
OptionalUserTokenHeaderDependency = Annotated[str | None, Depends(APIKeyHeader(name=USER_TOKEN_HEADER, auto_error=False))]


def get_app(request: Request) -> App:
    return request.app


AppDependency = Annotated[App, Depends(get_app)]


def get_session(app: AppDependency):
    with Session(app.db_engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def get_mutable_state(app: AppDependency) -> MutableState:
    return app.mutable_state


MutableStateDependency = Annotated[MutableState, Depends(get_mutable_state)]


def get_main_config(app: AppDependency) -> MainConfig:
    return app.main_config


MainConfigDependency = Annotated[MainConfig, Depends(get_main_config)]


def get_secret_config(app: AppDependency) -> SecretConfig:
    return app.secret_config


SecretConfigDependency = Annotated[SecretConfig, Depends(get_secret_config)]


def get_mandatory_user(state: MutableStateDependency, token: UserTokenHeaderDependency) -> UserReference:
    user = state.token_to_user.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


MandatoryUserDependency = Annotated[UserReference, Depends(get_mandatory_user)]


def get_mandatory_player_login(state: MutableStateDependency, token: UserTokenHeaderDependency) -> str:
    client = state.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    return client.login


MandatoryPlayerLoginDependency = Annotated[str, Depends(get_mandatory_player_login)]


def verify_admin(client_login: MandatoryPlayerLoginDependency, session: SessionDependency) -> None:
    if not session.get(PlayerRole, (UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")


def get_optional_player_login(state: MutableStateDependency, token: OptionalUserTokenHeaderDependency) -> str | None:
    if token is not None:
        client = state.token_to_user.get(token)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not client.is_guest():
            return client.login
    return None


OptionalPlayerLoginDependency = Annotated[str | None, Depends(get_optional_player_login)]
