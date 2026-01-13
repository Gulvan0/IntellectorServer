from src.rules.coords import HexCoordinates
from src.rules.piece import PieceColor, PieceKind, Piece
from src.rules.position import Position


def get_piece_kind(letter: str) -> PieceKind:
    match letter:
        case "r":
            return PieceKind.PROGRESSOR
        case "g":
            return PieceKind.AGGRESSOR
        case "e":
            return PieceKind.DEFENSOR
        case "i":
            return PieceKind.LIBERATOR
        case "o":
            return PieceKind.DOMINATOR
        case "n":
            return PieceKind.INTELLECTOR
        case _:
            raise ValueError(f"PieceKind not found for letter {letter}")


def get_piece_color(letter: str) -> PieceColor:
    return PieceColor.WHITE if letter == "w" else PieceColor.BLACK


def color_to_move_from_sip(sip: str) -> PieceColor:
    parts = sip.split('!', 2)
    letter = sip[0] if len(parts) == 2 else parts[1][0]
    return get_piece_color(letter)


def position_from_sip(sip: str) -> Position:
    position = Position()
    parts = sip.split('!', 2)
    if len(parts) == 2:
        version = 1
    else:
        version = int(parts.pop(0))
    match version:
        case 1:
            position.color_to_move = get_piece_color(parts[0][0])
            parts[0] = parts[0][1:]
            for color, part in zip([PieceColor.WHITE, PieceColor.BLACK], parts):
                for i in range(0, len(part), 2):
                    scalar_coord = ord(part[i]) - 64
                    hex_coords = HexCoordinates.from_scalar(scalar_coord)
                    piece_kind = get_piece_kind(part[i + 1])
                    position.piece_arrangement[hex_coords] = Piece(piece_kind, color)
        case 2:
            position.color_to_move = get_piece_color(parts[0][0])
            parts[0] = parts[0][1:]
            for color, part in zip([PieceColor.WHITE, PieceColor.BLACK], parts):
                for i in range(0, len(part), 2):
                    coords_char_code = ord(part[i])
                    if coords_char_code >= 97:
                        scalar_coord = 26 + coords_char_code - 97
                    elif coords_char_code >= 65:
                        scalar_coord = coords_char_code - 65
                    else:
                        scalar_coord = 52 + coords_char_code - 48
                    hex_coords = HexCoordinates.from_scalar(scalar_coord)
                    piece_kind = get_piece_kind(part[i + 1])
                    position.piece_arrangement[hex_coords] = Piece(piece_kind, color)
        case _:
            raise ValueError(f'Unknown version: {version}')
    return position
