from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import create_db_and_tables
from models import *  # noqa
from routers import study


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(study.router)


@app.get("/")
async def root():
    return {"message": "Hello World"}