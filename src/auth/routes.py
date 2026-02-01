from datetime import UTC, datetime
from hashlib import md5
from secrets import token_hex
from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute

from auth.models import AuthCredentials, PlayerPasswordUpdate, TokenResponse, GuestTokenResponse, PlayerPassword
from common.dependencies import MandatoryPlayerLoginDependency, MutableStateDependency, SessionDependency
from net.base_router import LoggingRoute

import bcrypt
import os

from player.datatypes import UserRole
from player.methods import create_player
from player.models import PlayerRole


route_class: type[APIRoute] = APIRoute
if os.getenv("STAGE", "").lower() == "test":  # To prevent password leakage
    route_class = LoggingRoute


router = APIRouter(prefix="/auth", route_class=route_class)


@router.post("/guest", response_model=GuestTokenResponse)
async def guest(state: MutableStateDependency) -> GuestTokenResponse:
    token = token_hex()
    guest_id = state.add_guest(token)
    return GuestTokenResponse(guest_id=guest_id, token=token)


@router.post("/signin", response_model=TokenResponse)
async def signin(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency) -> TokenResponse:
    login = credentials.login.lower()
    password_data = await session.get(PlayerPassword, login)
    if not password_data:
        raise HTTPException(status_code=404, detail="User not found")

    pwd_bytes = credentials.password.encode()
    if password_data.normal_md5:
        if md5(pwd_bytes).hexdigest() != password_data.normal_md5:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        password_data.created_at = datetime.now(UTC)
        password_data.password_hash = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt())
        password_data.normal_md5 = None
        session.add(password_data)
        await session.commit()
    elif not bcrypt.checkpw(pwd_bytes, password_data.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = token_hex()
    state.add_logged(token, login)
    return TokenResponse(token=token)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency) -> TokenResponse:
    login = credentials.login.lower()

    password_data = await session.get(PlayerPassword, login)
    if password_data:
        raise HTTPException(status_code=422, detail="User already exists")

    await create_player(
        session=session,
        login=login,
        nickname=credentials.login,  # case preserved!
        commit=False
    )

    password = PlayerPassword(
        login=login,
        password_hash=bcrypt.hashpw(credentials.password.encode(), bcrypt.gensalt())
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
) -> None:
    existing_admin_entry = await session.get(PlayerRole, (UserRole.ADMIN, client_login))
    if client_login != payload.login and not existing_admin_entry:
        raise HTTPException(status_code=403, detail="Forbidden")

    password_data = await session.get(PlayerPassword, payload.login)
    if not password_data:
        raise HTTPException(status_code=404, detail="User not found")

    password_data.created_at = datetime.now(UTC)
    password_data.normal_md5 = None
    password_data.password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt())
    session.add(password_data)
    await session.commit()
