from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, FischerTimeControlEntity, TimeControlKind
from .utils import CURRENT_DATETIME_COLUMN, PLAYER_REF_COLUMN, SIP_COLUMN, PLAYER_REF_COLUMN_DEFAULT_NONE


class ChallengeBase(SQLModel):
    acceptor_color: ChallengeAcceptorColor = ChallengeAcceptorColor.RANDOM
    custom_starting_sip: str | None = SIP_COLUMN
    rated: bool


class Challenge(ChallengeBase, table=True):
    id: int | None = Field(primary_key=True)
    created_at: datetime = CURRENT_DATETIME_COLUMN
    caller_ref: str = PLAYER_REF_COLUMN
    callee_ref: str | None = PLAYER_REF_COLUMN_DEFAULT_NONE
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool = True
    resulting_game_id: int | None = None

    # TODO: Game relationship
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControlBase(SQLModel, FischerTimeControlEntity):
    start_seconds: int = Field(gt=0, le=60 * 60 * 6)
    increment_seconds: int = Field(default=0, ge=0, le=60 * 2)


class ChallengeFischerTimeControl(ChallengeFischerTimeControlBase, table=True):
    challenge_id: int | None = Field(primary_key=True, foreign_key="challenge.id")

    challenge: Challenge = Relationship(back_populates="fischer_time_control")

    @classmethod
    def from_create_model(cls, model: ChallengeFischerTimeControlCreate | None) -> ChallengeFischerTimeControl | None:
        return ChallengeFischerTimeControl(**model.model_dump()) if model else None


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
    callee_ref: str | None = PLAYER_REF_COLUMN_DEFAULT_NONE
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool
    fischer_time_control: ChallengeFischerTimeControlPublic | None
    # TODO: resulting_game: GamePublic


class ChallengeCreateResponse(BaseModel):
    result: Literal["created", "merged"]
    challenge: ChallengePublic | None = None
    callee_online: bool | None = None
    game: Any | None = None  # TODO: Assign proper type
