import asyncio
from datetime import UTC, datetime
from hashlib import md5
from secrets import token_hex
from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from auth.models import AuthCredentials, PlayerPasswordUpdate, TokenResponse, GuestTokenResponse, WhoamiResponse, PlayerPassword
from common.dependencies import AppDependency, MainConfigDependency, MandatoryPlayerLoginDependency, MandatoryUserDependency, MutableStateDependency, SessionDependency
from common.models import UserRefWithNickname
from net.base_router import LoggingRoute, RateLimitedRoute, rate_limited
from net.rate_limit import RateLimitGroup
from net.utils.rest_error import RestErrorCode, RestException, rate_limited_error

import bcrypt

from config.stage import is_test_stage
from player.datatypes import UserRole
from player.methods import create_player, resolve_player_ref
from player.models import PlayerRole


route_class: type[RateLimitedRoute] = RateLimitedRoute
if is_test_stage():  # To prevent password leakage
    route_class = LoggingRoute


router = APIRouter(prefix="/auth", route_class=route_class)


async def hash_password(password: bytes) -> bytes:
    """In a thread, as hashing takes long enough to freeze every game on the server if done on the event loop"""
    return await asyncio.to_thread(lambda: bcrypt.hashpw(password, bcrypt.gensalt()))


@router.get("/guest", response_model=GuestTokenResponse)
@rate_limited(RateLimitGroup.GUEST)
async def guest(state: MutableStateDependency, main_config: MainConfigDependency) -> GuestTokenResponse:
    token = token_hex()
    guest_id = state.add_guest(token, main_config.limits.max_guest_tokens)
    return GuestTokenResponse(guest_id=guest_id, token=token)


@router.get("/whoami", response_model=WhoamiResponse)
async def whoami(user: MandatoryUserDependency, session: SessionDependency) -> WhoamiResponse:
    identity = await resolve_player_ref(user, session)
    return WhoamiResponse(
        user_ref=identity.user_ref,
        nickname=identity.nickname,
        guest_id=user.guest_id if user.is_guest() else None,
    )


@router.post("/signin", response_model=TokenResponse)
@rate_limited(RateLimitGroup.SIGNIN)
async def signin(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency, app: AppDependency) -> TokenResponse:
    login = credentials.login.lower()
    password_data = await session.get(PlayerPassword, login)
    if not password_data:
        raise RestException(RestErrorCode.USER_NOT_FOUND, "User not found")

    retry_after_secs = app.rate_limiter.take(RateLimitGroup.SIGNIN_FAILURES, login)
    if retry_after_secs is not None:
        raise rate_limited_error(retry_after_secs)

    pwd_bytes = credentials.password.encode()
    if password_data.normal_md5:
        if md5(pwd_bytes).hexdigest() != password_data.normal_md5:
            raise RestException(RestErrorCode.INVALID_CREDENTIALS, "Invalid credentials")

        password_data.created_at = datetime.now(UTC)
        password_data.password_hash = await hash_password(pwd_bytes)
        password_data.normal_md5 = None
        session.add(password_data)
        await session.commit()
    elif not await asyncio.to_thread(bcrypt.checkpw, pwd_bytes, password_data.password_hash):
        raise RestException(RestErrorCode.INVALID_CREDENTIALS, "Invalid credentials")

    app.rate_limiter.give_back(RateLimitGroup.SIGNIN_FAILURES, login)

    token = token_hex()
    state.add_logged(token, login)
    identity = await resolve_player_ref(login, session)
    return TokenResponse(token=token, identity=identity)


@router.post("/register", response_model=TokenResponse, status_code=201)
@rate_limited(RateLimitGroup.REGISTRATION)
async def register(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency) -> TokenResponse:
    login = credentials.login.lower()

    password_data = await session.get(PlayerPassword, login)
    if password_data:
        raise RestException(RestErrorCode.USER_ALREADY_EXISTS, "User already exists")

    password = PlayerPassword(
        login=login,
        password_hash=await hash_password(credentials.password.encode())
    )

    try:
        await create_player(
            session=session,
            login=login,
            nickname=credentials.login,  # case preserved!
            commit=False
        )
        session.add(password)
        await session.commit()
    except IntegrityError:  # a simultaneous registration of this login got ahead of this one
        await session.rollback()
        raise RestException(RestErrorCode.USER_ALREADY_EXISTS, "User already exists")

    token = token_hex()
    state.add_logged(token, login)
    identity = UserRefWithNickname(user_ref=login, nickname=credentials.login)  # case preserved!
    return TokenResponse(token=token, identity=identity)


@router.patch("/update_password", status_code=201)
@rate_limited(RateLimitGroup.SIGNIN)  # hashes a password just the same
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
        raise RestException(RestErrorCode.USER_NOT_FOUND, "User not found")

    password_data.created_at = datetime.now(UTC)
    password_data.normal_md5 = None
    password_data.password_hash = await hash_password(payload.password.encode())
    session.add(password_data)
    await session.commit()
