from typing import Literal
from pydantic import BaseModel, Field as PydanticField

from src.rules import PieceColor, PieceKind
from src.common.field_types import OptionalSip, PlayerRef
from src.game.datatypes import OutcomeKind
from src.game.models.time_control import GameFischerTimeControlCreate


class ExternalGameCreatePayload(BaseModel):
    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    custom_starting_sip: OptionalSip
    time_control: GameFischerTimeControlCreate


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
