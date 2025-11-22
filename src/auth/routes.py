from datetime import UTC, datetime
from secrets import token_hex
from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute

from src.auth.models import AuthCredentials, PlayerPasswordUpdate, TokenResponse, GuestTokenResponse, PlayerPassword
from src.common.dependencies import MandatoryPlayerLoginDependency, MutableStateDependency, SessionDependency
from src.net.base_router import LoggingRoute

import bcrypt  # type: ignore
import os
import src.player.methods as player_methods
import src.player.datatypes as player_datatypes
import src.player.models as player_models


route_class: type[APIRoute] = APIRoute
if os.getenv("STAGE", "").lower() == "test":  # To prevent password leakage
    route_class = LoggingRoute


router = APIRouter(prefix="/auth", route_class=route_class)


@router.post("/guest", response_model=GuestTokenResponse)
async def guest(state: MutableStateDependency):
    token = token_hex()
    guest_id = state.add_guest(token)
    return GuestTokenResponse(guest_id=guest_id, token=token)


@router.post("/signin", response_model=TokenResponse)
async def signin(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency):
    login = credentials.login.lower()
    password_data = await session.get(PlayerPassword, login)
    if not password_data:
        raise HTTPException(status_code=404, detail="User not found")
    if password_data.password_hash != bcrypt.hashpw(credentials.password, password_data.salt):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = token_hex()
    state.add_logged(token, login)
    return TokenResponse(token=token)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency):
    login = credentials.login.lower()

    password_data = await session.get(PlayerPassword, login)
    if password_data:
        raise HTTPException(status_code=400, detail="User already exists")

    await player_methods.create_player(
        session=session,
        login=login,
        nickname=credentials.login,  # case preserved!
        commit=False
    )

    salt = bcrypt.gensalt()
    password = PlayerPassword(
        login=login,
        salt=salt,
        password_hash=bcrypt.hashpw(credentials.password, salt)
    )
    session.add(password)
    await session.commit()

    token = token_hex()
    state.add_logged(token, login)
    return TokenResponse(token=token)


@router.patch("/update_password", status_code=201)
async def update_password(
    *,
    payload: PlayerPasswordUpdate,
    client_login: MandatoryPlayerLoginDependency,
    session: SessionDependency
):
    existing_admin_entry = await session.get(player_models.PlayerRole, (player_datatypes.UserRole.ADMIN, client_login))
    if client_login != payload.login and not existing_admin_entry:
        raise HTTPException(status_code=403, detail="Forbidden")

    password_data = await session.get(PlayerPassword, payload.login)
    if not password_data:
        raise HTTPException(status_code=404, detail="User not found")

    salt = bcrypt.gensalt()
    password_data.created_at = datetime.now(UTC)
    password_data.salt = salt
    password_data.password_hash = bcrypt.hashpw(payload.password, salt)
    session.add(password_data)
    await session.commit()
