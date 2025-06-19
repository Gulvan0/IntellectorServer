from datetime import datetime, UTC
from typing import Annotated

from sqlmodel import Field


PlayerRef = Annotated[str, Field(max_length=32)]
OptionalPlayerRef = Annotated[str | None, Field(max_length=32)]
Sip = Annotated[str, Field(max_length=127)]
OptionalSip = Annotated[str | None, Field(max_length=127)]
CurrentDatetime = Annotated[datetime, Field(default_factory=lambda: datetime.now(UTC))]
