from src.rules.piece import PieceKind
from src.common.field_types import Sip
from src.game.datatypes import OfferAction, OfferKind
from src.utils.custom_model import CustomModel


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
