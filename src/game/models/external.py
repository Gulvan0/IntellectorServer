from typing import Literal, Self
from pydantic import Field as PydanticField, model_validator

from src.rules.piece import PieceColor, PieceKind
from src.common.field_types import OptionalSip, PlayerRef
from src.game.datatypes import OutcomeKind, SimpleOutcome, TimeRemainders
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
    original_sip: OptionalSip
    time_remainders: TimeRemainders | None = None


class ExternalGameAppendPlyResponse(CustomModel):
    outcome: SimpleOutcome | None


class ExternalGameEndPayload(CustomModel):
    game_id: int
    outcome_kind: Literal[OutcomeKind.ABORT, OutcomeKind.ABANDON, OutcomeKind.DRAW_AGREEMENT, OutcomeKind.RESIGN]
    winner: PieceColor | None = None

    @model_validator(mode='after')
    def check_passwords_match(self) -> Self:
        if self.outcome_kind.drawish:
            if self.winner:
                raise ValueError("This outcome kind cannot have a winner")
        elif not self.winner:
            raise ValueError("This outcome kind should have a winner")
        return self


class ExternalGameRollbackPayload(CustomModel):
    game_id: int
    new_ply_cnt: int = PydanticField(ge=0)


class ExternalGameAddTimePayload(CustomModel):
    game_id: int
    receiver: PieceColor
