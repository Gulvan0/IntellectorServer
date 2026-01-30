from board.piece import PieceKind
from common.field_types import Sip
from game.datatypes import OfferAction, OfferKind, SimpleOutcome
from game.models.time_update import GameTimeUpdatePublic
from utils.custom_model import CustomModel


class InternalGameAppendPlyPayload(CustomModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
    original_sip: Sip | None = None


class InternalGameAppendPlyResponse(CustomModel):
    outcome: SimpleOutcome | None
    sip_after: Sip
    time_update: GameTimeUpdatePublic | None


class InternalGamePerformOfferActionPayload(CustomModel):
    game_id: int
    action_kind: OfferAction
    offer_kind: OfferKind
