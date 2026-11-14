from enum import StrEnum


USER_TOKEN_HEADER = "intellector-user-token"


class DbSchema(StrEnum):
    LOG = "intellector_logs"
    SENSITIVE = "intellector_sensitive"
