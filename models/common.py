from enum import auto, StrEnum

from pydantic import BaseModel, Field

from rules import PieceKind


class PieceKindField(StrEnum):
    PROGRESSOR = auto()
    AGGRESSOR = auto()
    DEFENSOR = auto()
    LIBERATOR = auto()
    DOMINATOR = auto()
    INTELLECTOR = auto()

    def to_piece_kind(self) -> PieceKind:
        match self:
            case PieceKindField.PROGRESSOR:
                return PieceKind.PROGRESSOR
            case PieceKindField.AGGRESSOR:
                return PieceKind.AGGRESSOR
            case PieceKindField.DEFENSOR:
                return PieceKind.DEFENSOR
            case PieceKindField.LIBERATOR:
                return PieceKind.LIBERATOR
            case PieceKindField.DOMINATOR:
                return PieceKind.DOMINATOR
            case PieceKindField.INTELLECTOR:
                return PieceKind.INTELLECTOR


class HexCoordsModel(BaseModel):
    i: int = Field(ge=0, le=8)
    j: int = Field(ge=0, le=6)


class PlyModel(BaseModel):
    departure: HexCoordsModel
    destination: HexCoordsModel
    morph_into: PieceKindField | None = None


class VariationNode(BaseModel):
    path: str
    ply: PlyModel


class PlyKindField(StrEnum):
    NORMAL = auto()
    CAPTURE = auto()
    SWAP = auto()


class PieceColorField(StrEnum):
    WHITE = auto()
    BLACK = auto()
