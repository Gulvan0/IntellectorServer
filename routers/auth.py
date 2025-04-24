from secrets import token_hex

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from globalstate import GlobalState
from models import AuthCredentials, Player, PlayerPassword
from .utils import get_session

import bcrypt

router = APIRouter(prefix="/auth")


@router.post("/signin", response_model=str)
async def signin(*, session: Session = Depends(get_session()), credentials: AuthCredentials):
    login = credentials.login.lower()
    password_data = session.get(PlayerPassword, login)
    if not password_data:
        raise HTTPException(status_code=404, detail="User not found")
    if password_data.password_hash != bcrypt.hashpw(credentials.password, password_data.salt):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = token_hex()
    GlobalState.token_to_login[token] = login
    return token


@router.post("/register", response_model=str, status_code=201)
async def register(*, session: Session = Depends(get_session()), credentials: AuthCredentials):
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
    GlobalState.token_to_login[token] = login
    return token