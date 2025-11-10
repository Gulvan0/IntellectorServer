from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

from models.game import Game, GamePublic
from utils.datatypes import ChallengeAcceptorColor, ChallengeKind, FischerTimeControlEntity, TimeControlKind
from utils.query import model_cast_optional
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
    resulting_game_id: int | None = Field(default=None, foreign_key="game.id")

    resulting_game: Game | None = Relationship()
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)

    def to_public(self, resulting_game: GamePublic | None) -> "ChallengePublic":
        return ChallengePublic(
            acceptor_color=self.acceptor_color,
            custom_starting_sip=self.custom_starting_sip,
            rated=self.rated,
            id=self.id,
            created_at=self.created_at,
            caller_ref=self.caller_ref,
            callee_ref=self.callee_ref,
            kind=self.kind,
            time_control_kind=self.time_control_kind,
            active=self.active,
            fischer_time_control=model_cast_optional(self.fischer_time_control, ChallengeFischerTimeControlPublic),
            resulting_game=resulting_game
        )


class ChallengeFischerTimeControlBase(SQLModel):
    start_seconds: int = Field(gt=0, le=60 * 60 * 6)
    increment_seconds: int = Field(default=0, ge=0, le=60 * 2)


if TYPE_CHECKING:
    _: type[FischerTimeControlEntity] = ChallengeFischerTimeControlBase


class ChallengeFischerTimeControl(ChallengeFischerTimeControlBase, table=True):
    challenge_id: int | None = Field(default=None, primary_key=True, foreign_key="challenge.id")

    challenge: Challenge = Relationship(back_populates="fischer_time_control")


class ChallengeFischerTimeControlPublic(ChallengeFischerTimeControlBase):
    pass


class ChallengeFischerTimeControlCreate(ChallengeFischerTimeControlBase):
    pass


class ChallengeCreateOpen(ChallengeBase):
    fischer_time_control: ChallengeFischerTimeControlCreate | None = None
    link_only: bool

    def to_db_challenge(self, caller_ref: str) -> Challenge:
        challenge_kind = ChallengeKind.LINK_ONLY if self.link_only else ChallengeKind.PUBLIC

        return Challenge(
            acceptor_color=self.acceptor_color,
            custom_starting_sip=self.custom_starting_sip,
            rated=self.rated,
            caller_ref=caller_ref,
            kind=challenge_kind,
            time_control_kind=TimeControlKind.of(self.fischer_time_control),
            fischer_time_control=model_cast_optional(self.fischer_time_control, ChallengeFischerTimeControl)
        )


class ChallengeCreateDirect(ChallengeBase):
    fischer_time_control: ChallengeFischerTimeControlCreate | None = None
    callee_ref: PlayerRef

    def to_db_challenge(self, caller_ref: str) -> Challenge:
        return Challenge(
            acceptor_color=self.acceptor_color,
            custom_starting_sip=self.custom_starting_sip,
            rated=self.rated,
            caller_ref=caller_ref,
            callee_ref=self.callee_ref,
            kind=ChallengeKind.DIRECT,
            time_control_kind=TimeControlKind.of(self.fischer_time_control),
            fischer_time_control=model_cast_optional(self.fischer_time_control, ChallengeFischerTimeControl)
        )


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
