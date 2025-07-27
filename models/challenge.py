from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

from models.game import Game, GamePublic
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, FischerTimeControlEntity, TimeControlKind
from .column_types import CurrentDatetime, PlayerRef, OptionalSip, OptionalPlayerRef


class ChallengeBase(SQLModel):
    acceptor_color: ChallengeAcceptorColor = ChallengeAcceptorColor.RANDOM
    custom_starting_sip: OptionalSip
    rated: bool


class Challenge(ChallengeBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: CurrentDatetime
    caller_ref: PlayerRef
    callee_ref: OptionalPlayerRef = None
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool = True
    vk_announcement_message_id: int | None = None
    resulting_game_id: int | None = Field(default=None, foreign_key="game.id")

    resulting_game: Game | None = Relationship()
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControlBase(SQLModel):
    start_seconds: int = Field(gt=0, le=60 * 60 * 6)
    increment_seconds: int = Field(default=0, ge=0, le=60 * 2)


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = ChallengeFischerTimeControlBase


class ChallengeFischerTimeControl(ChallengeFischerTimeControlBase, table=True):
    challenge_id: int | None = Field(default=None, primary_key=True, foreign_key="challenge.id")

    challenge: Challenge = Relationship(back_populates="fischer_time_control")

    @classmethod
    def from_create_model(cls, model: Optional["ChallengeFischerTimeControlCreate"]) -> Optional["ChallengeFischerTimeControl"] | None:
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
    callee_ref: PlayerRef


class ChallengePublic(ChallengeBase):
    id: int
    created_at: datetime
    caller_ref: PlayerRef
    callee_ref: OptionalPlayerRef
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool
    fischer_time_control: ChallengeFischerTimeControlPublic | None = None
    resulting_game: GamePublic | None = None


class ChallengeCreateResponse(BaseModel):
    result: Literal["created", "merged"]
    challenge: ChallengePublic | None = None
    callee_online: bool | None = None
    game: GamePublic | None = None


class ChallengeListStateRefresh(BaseModel):
    challenges: list[Challenge]


class SpecificUserChallengeListStateRefresh(ChallengeListStateRefresh):
    user_ref: str
