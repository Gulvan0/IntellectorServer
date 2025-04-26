from sqlmodel import create_engine
from models import *

from globalstate import GlobalState


engine = create_engine(GlobalState.secret_config.db.url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
