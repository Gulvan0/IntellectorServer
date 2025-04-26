from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import create_db_and_tables
from models import *  # noqa
from routers import study, player, auth, other


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(study.router)
app.include_router(auth.router)
app.include_router(player.router)
app.include_router(other.router)
