from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, TimeControlKind
from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN, SIP_COLUMN


class Challenge(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    created_at: datetime = CURRENT_DATETIME_COLUMN
    caller_ref: str = PLAYER_REF_COLUMN
    callee_ref: str = PLAYER_REF_COLUMN
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    acceptor_color: ChallengeAcceptorColor = ChallengeAcceptorColor.RANDOM
    custom_starting_sip: str | None = SIP_COLUMN
    rated: bool
    active: bool
    resulting_game_id: int

    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControl(SQLModel, table=True):
    challenge_id: int | None = Field(primary_key=True, foreign_key="challenge.id")
    start_seconds: int
    increment_seconds: int = 0

    challenge: Challenge = Relationship(back_populates="fischer_time_control")