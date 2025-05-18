from datetime import datetime, UTC

from sqlmodel import Field


PLAYER_REF_COLUMN = Field(max_length=32)
SIP_COLUMN = Field(max_length=127)
CURRENT_DATETIME_COLUMN = Field(default_factory=lambda: datetime.now(UTC))
PLAYER_REF_COLUMN_DEFAULT_NONE = Field(max_length=32, default=None)
