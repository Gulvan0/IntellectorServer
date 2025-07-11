from secrets import token_hex

from fastapi import APIRouter, HTTPException
from models import AuthCredentials, Player, PlayerPassword, TokenResponse
from models.auth import GuestTokenResponse
from .utils import MutableStateDependency, SessionDependency

import bcrypt  # type: ignore


router = APIRouter(prefix="/auth")


@router.post("/guest", response_model=GuestTokenResponse)
async def guest(state: MutableStateDependency):
    token = token_hex()
    guest_id = state.add_guest(token)
    return GuestTokenResponse(guest_id=guest_id, token=token)


@router.post("/signin", response_model=TokenResponse)
async def signin(*, credentials: AuthCredentials, session: SessionDependency, state: MutableStateDependency):
    login = credentials.login.lower()
    password_data = session.get(PlayerPassword, login)
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

    password_data = session.get(Player, login)
    if password_data:
        raise HTTPException(status_code=400, detail="User already exists")

    salt = bcrypt.gensalt()
    player = Player(
        login=login,
        nickname=credentials.login,  # case preserved!
        password=PlayerPassword(
            salt=salt,
            password_hash=bcrypt.hashpw(credentials.password, salt)
        )
    )
    session.add(player)
    session.commit()

    token = token_hex()
    state.add_logged(token, login)
    return TokenResponse(token=token)
