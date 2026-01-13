from src.rules.coords import HexCoordinates
from src.rules.piece import Piece, PieceKind
from src.rules.ply import DerivedPlyProperties, Ply, PlyKind
from src.rules.position import Position


def piece_kind_mark(piece_kind: PieceKind) -> str:
    match piece_kind:
        case PieceKind.PROGRESSOR:
            return ""
        case PieceKind.AGGRESSOR:
            return "A"
        case PieceKind.DOMINATOR:
            return "D"
        case PieceKind.LIBERATOR:
            return "L"
        case PieceKind.DEFENSOR:
            return "F"
        case PieceKind.INTELLECTOR:
            return "I"


def column_letter(hex_coords: HexCoordinates) -> str:
    return chr(ord('a') + hex_coords.i)


def row_number(hex_coords: HexCoordinates) -> int:
    return 7 - hex_coords.j - hex_coords.i % 2


def hex_notation(hex_coords: HexCoordinates, caps: bool = False) -> str:
    raw = column_letter(hex_coords) + str(row_number(hex_coords))
    return raw.upper() if caps else raw


def __write_ply_resolved(ply: Ply, context_position: Position, moving_piece: Piece, target_piece: Piece | None, ply_kind: PlyKind) -> str:
    if ply_kind == PlyKind.SWAP:
        assert target_piece
        departure_str = hex_notation(ply.departure, caps=True)
        destination_str = hex_notation(ply.destination, caps=True)
        if target_piece.kind == PieceKind.INTELLECTOR:  # Always start with Intellector's position
            return f"{destination_str}:{departure_str}"
        else:
            return f"{departure_str}:{destination_str}"

    ply_notation = piece_kind_mark(moving_piece.kind)

    needs_specification = False
    for coords, piece in context_position.piece_arrangement.items():
        if coords != ply.departure and piece == moving_piece:
            for other_ply in context_position.available_plys_from_hex(coords, piece):
                if ply.destination == other_ply.destination:
                    needs_specification = True
                    break
            if needs_specification:
                break

    if needs_specification:
        ply_notation += hex_notation(ply.departure)

    if ply_kind == PlyKind.CAPTURE:
        ply_notation += "X"
    elif needs_specification:
        ply_notation += "~"

    ply_notation += hex_notation(ply.destination)

    if ply.morph_into:
        ply_notation += "=" + piece_kind_mark(ply.morph_into)

    if ply_kind == PlyKind.CAPTURE:
        assert target_piece
        if target_piece.kind == PieceKind.INTELLECTOR:  # Fatum
            ply_notation += "#"

    return ply_notation


def write_ply(ply: Ply, context_position: Position, properties: DerivedPlyProperties | None = None) -> str:
    if not properties:
        properties = DerivedPlyProperties.from_pieces(
            moving_piece=context_position.piece_arrangement[ply.departure],
            target_piece=context_position.piece_arrangement.get(ply.destination)
        )

    return __write_ply_resolved(ply, context_position, properties.moving_piece, properties.target_piece, properties.ply_kind)
