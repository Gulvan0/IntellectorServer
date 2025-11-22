from typing import Annotated
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from src.common.constants import USER_TOKEN_HEADER
from src.common.user_ref import UserReference
from src.config.models import MainConfig, SecretConfig
from src.net.core import App, MutableState

import src.player.models as player_models
import src.player.datatypes as player_datatypes
from src.utils.async_orm_session import AsyncSession


UserTokenHeaderDependency = Annotated[str, Depends(APIKeyHeader(name=USER_TOKEN_HEADER))]
OptionalUserTokenHeaderDependency = Annotated[str | None, Depends(APIKeyHeader(name=USER_TOKEN_HEADER, auto_error=False))]


async def get_app(request: Request) -> App:
    return request.app


AppDependency = Annotated[App, Depends(get_app)]


async def get_session(app: AppDependency):
    async with AsyncSession(app.db_engine) as session:
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_mutable_state(app: AppDependency) -> MutableState:
    return app.mutable_state


MutableStateDependency = Annotated[MutableState, Depends(get_mutable_state)]


async def get_main_config(app: AppDependency) -> MainConfig:
    return app.main_config


MainConfigDependency = Annotated[MainConfig, Depends(get_main_config)]


async def get_secret_config(app: AppDependency) -> SecretConfig:
    return app.secret_config


SecretConfigDependency = Annotated[SecretConfig, Depends(get_secret_config)]


async def get_mandatory_user(state: MutableStateDependency, token: UserTokenHeaderDependency) -> UserReference:
    user = state.token_to_user.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


MandatoryUserDependency = Annotated[UserReference, Depends(get_mandatory_user)]


async def get_mandatory_player_login(state: MutableStateDependency, token: UserTokenHeaderDependency) -> str:
    client = state.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    return client.login


MandatoryPlayerLoginDependency = Annotated[str, Depends(get_mandatory_player_login)]


async def verify_admin(client_login: MandatoryPlayerLoginDependency, session: SessionDependency) -> None:
    if not session.get(player_models.PlayerRole, (player_datatypes.UserRole.ADMIN, client_login)):
        raise HTTPException(status_code=403, detail="Forbidden")


async def get_optional_player_login(state: MutableStateDependency, token: OptionalUserTokenHeaderDependency) -> str | None:
    if token is not None:
        client = state.token_to_user.get(token)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not client.is_guest():
            return client.login
    return None


OptionalPlayerLoginDependency = Annotated[str | None, Depends(get_optional_player_login)]
