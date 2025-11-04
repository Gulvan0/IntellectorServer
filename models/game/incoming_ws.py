from pydantic import BaseModel

from rules import PieceKind

from ..column_types import Sip
from utils.datatypes import OfferAction, OfferKind


class PlyIntentData(BaseModel):
    game_id: int
    from_i: int
    from_j: int
    to_i: int
    to_j: int
    morph_into: PieceKind | None = None
    sip_after: Sip | None = None


class ChatMessageIntentData(BaseModel):
    game_id: int
    text: str


class OfferActionIntentData(BaseModel):
    game_id: int
    action_kind: OfferAction
    offer_kind: OfferKind


class AddTimeIntentData(BaseModel):
    game_id: int
