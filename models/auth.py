from pydantic import BaseModel, Field as PydanticField


class AuthCredentials(BaseModel):
    login: str = PydanticField(min_length=2, max_length=32, pattern=r'^[a-zA-Z]([_\-]?[a-zA-Z0-9]+)+$')
    password: str = PydanticField(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    token: str


class GuestTokenResponse(BaseModel):
    guest_id: int
    token: str
