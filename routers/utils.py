from fastapi.security import APIKeyHeader
from sqlmodel import Session

from database import engine


def get_session():
    with Session(engine) as session:
        yield session


USER_TOKEN_HEADER_SCHEME = APIKeyHeader(name="intellector-user-token")
OPTIONAL_USER_TOKEN_HEADER_SCHEME = APIKeyHeader(name="intellector-user-token", auto_error=False)
