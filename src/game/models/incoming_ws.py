from board.piece import PieceKind
from common.field_types import Sip
from game.datatypes import OfferAction, OfferKind
from utils.custom_model import CustomModel


class PlyIntentData(CustomModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
    original_sip: Sip | None = None


class ChatMessageIntentData(CustomModel):
    game_id: int
    text: str


class OfferActionIntentData(CustomModel):
    game_id: int
    action_kind: OfferAction
    offer_kind: OfferKind


class AddTimeIntentData(CustomModel):
    game_id: int
