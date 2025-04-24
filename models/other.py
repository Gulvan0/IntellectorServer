from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


class AuthCredentials(BaseModel):
    login: str = PydanticField(min_length=2, max_length=32, pattern=r'^([@#\$\.]?\w)+[@#\$\.]?$')
    password: str = PydanticField(min_length=6, max_length=128)


class SavedQuery(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)