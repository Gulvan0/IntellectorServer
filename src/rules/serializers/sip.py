from src.rules.piece import PieceKind, PieceColor
from src.rules.position import Position


def piece_letter(piece_kind: PieceKind) -> str:
    match piece_kind:
        case PieceKind.PROGRESSOR:
            return "r"
        case PieceKind.AGGRESSOR:
            return "g"
        case PieceKind.DEFENSOR:
            return "e"
        case PieceKind.LIBERATOR:
            return "i"
        case PieceKind.DOMINATOR:
            return "o"
        case PieceKind.INTELLECTOR:
            return "n"


def color_letter(piece_color: PieceColor) -> str:
    return "w" if piece_color == PieceColor.WHITE else "b"


def get_sip(position: Position) -> str:
    pieces: dict[PieceColor, list[tuple[int, PieceKind]]] = {PieceColor.WHITE: [], PieceColor.BLACK: []}
    for hex_coords, piece in position.piece_arrangement.items():
        pieces[piece.color].append((hex_coords.scalar, piece.kind))
    arrangement_strings = {PieceColor.WHITE: "", PieceColor.BLACK: ""}
    for color, piece_position_tuples in pieces.items():
        for scalar_coord, piece_kind in sorted(piece_position_tuples):
            match scalar_coord // 26:
                case 0:
                    starting_ascii_index = 65  # capital letters
                case 1:
                    starting_ascii_index = 97  # small letters
                case _:
                    starting_ascii_index = 48  # digits
            arrangement_strings[color] += chr(starting_ascii_index + scalar_coord % 26) + piece_letter(piece_kind)
    return f"2!{color_letter(position.color_to_move)}{arrangement_strings[PieceColor.WHITE]}!{arrangement_strings[PieceColor.BLACK]}"


def get_v1_sip(position: Position) -> str:
    pieces: dict[PieceColor, list[tuple[int, PieceKind]]] = {PieceColor.WHITE: [], PieceColor.BLACK: []}
    for hex_coords, piece in position.piece_arrangement.items():
        pieces[piece.color].append((hex_coords.scalar, piece.kind))
    arrangement_strings = {PieceColor.WHITE: "", PieceColor.BLACK: ""}
    for color, piece_position_tuples in pieces.items():
        for scalar_coord, piece_kind in sorted(piece_position_tuples):
            arrangement_strings[color] += chr(64 + scalar_coord) + piece_letter(piece_kind)
    return f"{color_letter(position.color_to_move)}{arrangement_strings[PieceColor.WHITE]}!{arrangement_strings[PieceColor.BLACK]}"
