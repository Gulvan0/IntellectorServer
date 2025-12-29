from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional
from sqlmodel import Field, Relationship

from src.challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from src.common.models import UserRefWithNickname
from src.common.time_control import FischerTimeControlEntity, TimeControlKind
from src.common.field_types import CurrentDatetime, PlayerRef, OptionalSip, OptionalPlayerRef
from src.utils.custom_model import CustomModel, CustomSQLModel

import src.game.models.main as game_models


class ChallengeBase(CustomSQLModel):
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

    resulting_game: game_models.Game | None = Relationship()
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)


class ChallengeFischerTimeControlBase(CustomSQLModel):
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
            fischer_time_control=ChallengeFischerTimeControl.cast(self.fischer_time_control)
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
            fischer_time_control=ChallengeFischerTimeControl.cast(self.fischer_time_control)
        )


class ChallengePublic(ChallengeBase):
    id: int
    created_at: datetime
    caller: UserRefWithNickname
    callee: UserRefWithNickname | None
    kind: ChallengeKind
    time_control_kind: TimeControlKind
    active: bool
    fischer_time_control: ChallengeFischerTimeControlPublic | None = None
    resulting_game: game_models.GamePublic | None = None


class ChallengeCreateResponse(CustomModel):
    result: Literal["created", "merged"]
    challenge: ChallengePublic | None = None
    callee_online: bool | None = None
    game: game_models.GamePublic | None = None


class ChallengeListStateRefresh(CustomModel):
    challenges: list[ChallengePublic]
