from pydantic import BaseModel


class EmptyModel(BaseModel):
    pass


class Id(BaseModel):
    id: int
