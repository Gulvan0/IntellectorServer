from typing import Literal
from pydantic import Field as PydanticField

from src.rules import PieceColor, PieceKind
from src.common.field_types import OptionalSip, PlayerRef
from src.game.datatypes import OutcomeKind
from src.game.models.time_control import GameFischerTimeControlCreate
from src.utils.custom_model import CustomModel


class ExternalGameCreatePayload(CustomModel):
    white_player_ref: PlayerRef
    black_player_ref: PlayerRef
    custom_starting_sip: OptionalSip
    time_control: GameFischerTimeControlCreate


class ExternalGameAppendPlyPayload(CustomModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
    white_ms_after_execution: int | None = None
    black_ms_after_execution: int | None = None


class SimpleOutcome(CustomModel):
    kind: OutcomeKind
    winner: PieceColor | None = None


class ExternalGameAppendPlyResponse(CustomModel):
    outcome: SimpleOutcome | None


class ExternalGameEndPayload(CustomModel):
    game_id: int
    outcome_kind: Literal[OutcomeKind.ABORT, OutcomeKind.ABANDON, OutcomeKind.DRAW_AGREEMENT, OutcomeKind.RESIGN]
    winner: PieceColor | None = None


class ExternalGameRollbackPayload(CustomModel):
    game_id: int
    new_ply_cnt: int = PydanticField(ge=0)


class ExternalGameAddTimePayload(CustomModel):
    game_id: int
    receiver: PieceColor
