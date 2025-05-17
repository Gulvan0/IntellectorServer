from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, TimeControlKind
from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN, SIP_COLUMN


class ChallengeBase(SQLModel):
    acceptor_color: ChallengeAcceptorColor = ChallengeAcceptorColor.RANDOM
    custom_starting_sip: str | None = SIP_COLUMN
    rated: bool


class Challenge(ChallengeBase, table=True):
    id: int | None = Field(primary_key=True)
    created_at: datetime = CURRENT_DATETIME_COLUMN
    caller_ref: str = PLAYER_REF_COLUMN
    callee_ref: str | None = PLAYER_REF_COLUMN
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool
    resulting_game_id: int | None = None

    # TODO: Game relationship
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControlBase(SQLModel):
    start_seconds: int = Field(gt=0, le=60 * 60 * 6)
    increment_seconds: int = Field(default=0, ge=0, le=60 * 2)


class ChallengeFischerTimeControl(ChallengeFischerTimeControlBase, table=True):
    challenge_id: int | None = Field(primary_key=True, foreign_key="challenge.id")

    challenge: Challenge = Relationship(back_populates="fischer_time_control")


class ChallengeFischerTimeControlPublic(ChallengeFischerTimeControlBase):
    pass


class ChallengeFischerTimeControlCreate(ChallengeFischerTimeControlBase):
    pass


class ChallengeCreateOpen(ChallengeBase):
    fischer_time_control: ChallengeFischerTimeControlCreate | None = None
    link_only: bool


class ChallengeCreateDirect(ChallengeBase):
    fischer_time_control: ChallengeFischerTimeControlCreate | None = None
    callee_ref: str = PLAYER_REF_COLUMN


class ChallengePublic(ChallengeBase):
    id: int
    created_at: datetime
    caller_ref: str = PLAYER_REF_COLUMN
    callee_ref: str | None = PLAYER_REF_COLUMN
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool
    fischer_time_control: ChallengeFischerTimeControlPublic | None
    # TODO: resulting_game: GamePublic