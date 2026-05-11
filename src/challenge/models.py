from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional
from sqlalchemy.orm import Load, joinedload
from sqlmodel import Field, Relationship

from challenge.datatypes import ChallengeAcceptorColor, ChallengeKind
from common.models import UserRefWithNickname
from common.resolved_refs import ResolvedRefs
from common.time_control import FischerTimeControlEntity, TimeControlKind
from common.field_types import CurrentDatetime, PlayerRef, OptionalSip, OptionalPlayerRef
from game.models.main import Game, GameSummaryPublic
from utils.custom_model import CustomModel, CustomSQLModel


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

    resulting_game: Game | None = Relationship()
    fischer_time_control: Optional["ChallengeFischerTimeControl"] = Relationship(back_populates="challenge", cascade_delete=True)

    @classmethod
    def load_options(cls) -> list[Load]:
        return [
            joinedload(Challenge.resulting_game)
                .options(*Game.load_options(just_summary=True)),  # noqa: E131
            joinedload(Challenge.fischer_time_control),
        ]

    def collect_refs(self, include_nested: bool) -> set[str]:
        refs = {self.caller_ref}
        if self.callee_ref:
            refs.add(self.callee_ref)
        if include_nested and self.resulting_game:
            refs |= self.resulting_game.collect_refs(include_nested=False)
        return refs

    def __to_public_generic(
        self,
        resolved_refs: ResolvedRefs,
        fischer_time_control: ChallengeFischerTimeControl | None,
        resulting_game: GameSummaryPublic | None
    ) -> ChallengePublic:
        return ChallengePublic(
            acceptor_color=self.acceptor_color,
            custom_starting_sip=self.custom_starting_sip,
            rated=self.rated,
            id=self.id,
            created_at=self.created_at,
            caller=resolved_refs.get(self.caller_ref),
            callee=resolved_refs.get(self.callee_ref) if self.callee_ref else None,
            kind=self.kind,
            time_control_kind=self.time_control_kind,
            active=self.active,
            fischer_time_control=ChallengeFischerTimeControlPublic.cast(fischer_time_control),
            resulting_game=resulting_game
        )

    def to_public(self, resolved_refs: ResolvedRefs) -> ChallengePublic:
        return self.__to_public_generic(
            resolved_refs,
            self.fischer_time_control,
            self.resulting_game.to_summary(resolved_refs) if self.resulting_game else None
        )

    def to_public_as_fresh(self, resolved_refs: ResolvedRefs, fischer_time_control: ChallengeFischerTimeControl | None) -> ChallengePublic:
        return self.__to_public_generic(resolved_refs, fischer_time_control, None)


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
    resulting_game: GameSummaryPublic | None = None


class ChallengeCreateResponse(CustomModel):
    result: Literal["CREATED", "MERGED"]
    challenge: ChallengePublic | None = None
    callee_online: bool | None = None
    game: GameSummaryPublic | None = None
