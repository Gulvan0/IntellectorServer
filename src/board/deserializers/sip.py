from board.coords import HexCoordinates
from board.piece import PieceColor, PieceKind, Piece
from board.position import Position


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
    match letter:
        case "w":
            return PieceColor.WHITE
        case "b":
            return PieceColor.BLACK
        case _:
            raise ValueError(f"PieceColor not found for letter {letter}")


def _split_versioned(sip: str) -> tuple[int, list[str]]:
    """The version and the two arrangements, the first one led by the color to move. A SIP with no version prefix is a v1 one"""
    parts = sip.split('!')
    match len(parts):
        case 2:
            version = 1
        case 3:
            if not parts[0].isascii() or not parts[0].isdecimal():
                raise ValueError(f"Invalid SIP version: {parts[0]}")
            version = int(parts.pop(0))
        case _:
            raise ValueError(f"Invalid SIP: {sip}")
    if not parts[0]:
        raise ValueError(f"No color to move in SIP: {sip}")
    return version, parts


def color_to_move_from_sip(sip: str) -> PieceColor:
    _, parts = _split_versioned(sip)
    return get_piece_color(parts[0][0])


def _v1_scalar_coord(char: str) -> int:
    return ord(char) - 64


def _v2_scalar_coord(char: str) -> int:
    if not char.isascii() or not char.isalnum():
        raise ValueError(f"Invalid SIP coordinate: {char}")

    char_code = ord(char)
    if char_code >= 97:
        return 26 + char_code - 97
    if char_code >= 65:
        return char_code - 65
    return 52 + char_code - 48


def position_from_sip(sip: str) -> Position:
    """Raises ValueError for anything but a position's SIP. Doesn't judge whether the position could occur in a game"""
    version, parts = _split_versioned(sip)
    match version:
        case 1:
            scalar_coord_of = _v1_scalar_coord
        case 2:
            scalar_coord_of = _v2_scalar_coord
        case _:
            raise ValueError(f'Unknown version: {version}')

    position = Position()
    position.color_to_move = get_piece_color(parts[0][0])
    parts[0] = parts[0][1:]
    for color, part in zip([PieceColor.WHITE, PieceColor.BLACK], parts):
        if len(part) % 2:
            raise ValueError(f"Incomplete SIP arrangement: {part}")
        for i in range(0, len(part), 2):
            scalar_coord = scalar_coord_of(part[i])
            hex_coords = HexCoordinates.from_scalar(scalar_coord)
            if scalar_coord < 0 or not hex_coords.is_valid():
                raise ValueError(f"Invalid SIP coordinate: {part[i]}")
            if hex_coords in position.piece_arrangement:
                raise ValueError(f"Two pieces on a single hex in SIP: {sip}")
            piece_kind = get_piece_kind(part[i + 1])
            position.piece_arrangement[hex_coords] = Piece(piece_kind, color)
    return position
