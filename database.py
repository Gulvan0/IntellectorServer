import os

from sqlmodel import SQLModel, create_engine


url = os.getenv("DB_URL") or f"mysql://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_SCHEMA")}"
engine = create_engine(url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
