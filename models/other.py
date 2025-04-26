from sqlmodel import Field, SQLModel


class SavedQuery(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)