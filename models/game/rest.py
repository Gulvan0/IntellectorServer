from typing import TYPE_CHECKING, Literal
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import ColumnElement
from sqlmodel import or_
from .main import Game
from rules import PieceColor, PieceKind
from ..column_types import OptionalSip, PlayerRef, OptionalPlayerRef
from utils.datatypes import OutcomeKind, TimeControlKind


if TYPE_CHECKING:
    from .time_control import GameFischerTimeControlCreate


class GameFilter(BaseModel):
    player_ref: OptionalPlayerRef = None
    time_control_kind: TimeControlKind | None = None

    def construct_conditions(self) -> list[bool | ColumnElement[bool]]:
        conditions: list[bool | ColumnElement[bool]] = []
        if self.player_ref:
            conditions.append(or_(
                Game.white_player_ref == self.player_ref,
                Game.black_player_ref == self.player_ref
            ))
        if self.time_control_kind:
            conditions.append(Game.time_control_kind == self.time_control_kind)
        return conditions


class ExternalGameCreatePayload(BaseModel):
    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    custom_starting_sip: OptionalSip
    time_control: GameFischerTimeControlCreate | None


class ExternalGameAppendPlyPayload(BaseModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
    white_ms_after_execution: int | None = None
    black_ms_after_execution: int | None = None


class SimpleOutcome(BaseModel):
    kind: OutcomeKind
    winner: PieceColor | None = None


class ExternalGameAppendPlyResponse(BaseModel):
    outcome: SimpleOutcome | None


class ExternalGameEndPayload(BaseModel):
    game_id: int
    outcome_kind: Literal[OutcomeKind.ABORT, OutcomeKind.ABANDON, OutcomeKind.DRAW_AGREEMENT, OutcomeKind.RESIGN]
    winner: PieceColor | None = None


class ExternalGameRollbackPayload(BaseModel):
    game_id: int
    new_ply_cnt: int = PydanticField(ge=0)


class ExternalGameAddTimePayload(BaseModel):
    game_id: int
    receiver: PieceColor
