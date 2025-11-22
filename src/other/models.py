from sqlmodel import Field

from src.other.datatypes import CompatibilityResolution
from src.utils.custom_model import CustomModel, CustomSQLModel


class SavedQuery(CustomSQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    author_login: str
    is_private: bool
    name: str = Field(max_length=64)
    text: str = Field(max_length=2000)


class CompatibilityCheckPayload(CustomModel):
    client_build: int
    min_server_build: int


class CompatibilityResponse(CustomModel):
    resolution: CompatibilityResolution
    server_build: int
    min_client_build: int
