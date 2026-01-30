from random import randint, random
from board.constants.common import BOARD_HEX_COUNT
from board.coords import HexCoordinates
from board.piece import Piece, PieceColor, PieceKind
from board.ply import Ply
from board.position import Position, PositionFinalityGroup
from board.serializers.sip import get_sip


def piece_color() -> PieceColor:
    return PieceColor.WHITE if random() > 0.5 else PieceColor.BLACK


def hex_coords(start_offset: int = 0, end_offset: int = 0) -> HexCoordinates:
    return HexCoordinates.from_scalar(randint(start_offset, BOARD_HEX_COUNT - 1 - end_offset))


def non_final_row_hex_coords(piece_color: PieceColor | None = None) -> HexCoordinates:
    return hex_coords(
        start_offset=0 if piece_color == PieceColor.BLACK else 5,
        end_offset=0 if piece_color == PieceColor.WHITE else 5
    )


def valid_progressor_hex_coords(piece_color: PieceColor | None = None) -> HexCoordinates:
    return hex_coords(
        start_offset=9 if piece_color == PieceColor.BLACK else 5,
        end_offset=9 if piece_color == PieceColor.WHITE else 5
    )


def valid_non_final_position() -> Position:
    piece_arrangement = {}

    for color in PieceColor:  # Separate loops so that not only black pieces can override previously assigned hexes
        for _ in range(5):
            if random() < 0.5:
                piece_arrangement[valid_progressor_hex_coords(color)] = Piece(PieceKind.PROGRESSOR, color)

    for color in PieceColor:
        for kind in PieceKind.affected_by_aura():
            for _ in range(2):
                if random() < 0.7:
                    piece_arrangement[hex_coords()] = Piece(kind, color)

    for color in PieceColor:
        piece_arrangement[non_final_row_hex_coords(color)] = Piece(PieceKind.INTELLECTOR, color)

    return Position(
        piece_arrangement=piece_arrangement,
        color_to_move=piece_color()
    )


def valid_non_final_sip() -> str:
    return get_sip(valid_non_final_position())


def non_default_starting_position() -> Position:
    return valid_non_final_position()  # Will probably suffice


def non_default_starting_sip() -> str:
    return get_sip(non_default_starting_position())


def playthrough(position: Position, length: int = 5) -> list[Ply]:
    result = []

    for _ in range(length):
        possible_plys = position.available_plys()
        while possible_plys:
            random_index = randint(0, len(possible_plys) - 1)
            ply = possible_plys.pop(random_index)
            new_position = position.perform_ply(ply).new_position
            if new_position.get_finality_group() == PositionFinalityGroup.VALID_NON_FINAL:
                result.append(ply)
                position = new_position
                break

    return result
