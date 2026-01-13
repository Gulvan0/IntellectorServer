from typing import TYPE_CHECKING
from src.rules.coords import HexCoordinates
from src.rules.piece import Piece, PieceColor, PieceKind
from src.rules.piece_movement import PieceMovementDirection
from src.rules.ply import DerivedPlyProperties, Ply, PlyKind


if TYPE_CHECKING:
    from src.rules.position import Position


class PlyImpossibleException(Exception):
    pass


def __require(cond) -> None:
    if not cond:
        raise PlyImpossibleException


def __validate_capture_or_normal(ply: Ply, properties: DerivedPlyProperties, position: "Position", aura_allowed: bool = True):
    __require(properties.ply_kind != PlyKind.SWAP)
    if ply.morph_into:
        __require(aura_allowed)
        __require(properties.target_piece == Piece(ply.morph_into, properties.moving_piece.color.opposite()))
        __require(ply.morph_into not in (properties.moving_piece.kind, PieceKind.INTELLECTOR))
        __require(position.is_hex_under_aura(ply.departure, properties.moving_piece.color))


def __validate_raycast_reachability(ply: Ply, position: "Position", absolute_direction: PieceMovementDirection):
    currently_iterated_hex_coords = ply.departure.step(absolute_direction)
    __require(currently_iterated_hex_coords is not None)
    assert currently_iterated_hex_coords
    while currently_iterated_hex_coords.i != ply.destination.i:
        __require(not position.piece_arrangement.get(currently_iterated_hex_coords))
        currently_iterated_hex_coords = currently_iterated_hex_coords.step(absolute_direction)
        __require(currently_iterated_hex_coords is not None)
        assert currently_iterated_hex_coords
    __require(currently_iterated_hex_coords.j == ply.destination.j)


def validate_progressor_ply(ply: Ply, properties: DerivedPlyProperties, position: "Position", allow_aura_captures: bool = False) -> None:
    __require(-1 <= ply.destination.i - ply.departure.i <= 1)
    if (ply.departure.i % 2 == 0) == (properties.moving_piece.color == PieceColor.WHITE):
        required_delta = -1 if properties.moving_piece.color == PieceColor.WHITE else 1
        __require(ply.destination.j - ply.departure.j == required_delta)
    else:
        if ply.destination.i == ply.departure.i:
            required_delta = -1 if properties.moving_piece.color == PieceColor.WHITE else 1
            __require(ply.destination.j - ply.departure.j == required_delta)
        else:
            __require(ply.destination.j == ply.departure.j)
    if ply.destination.is_final_row_for(properties.moving_piece.color):
        if ply.morph_into not in PieceKind.promotion_options():
            __require(properties.target_piece and properties.target_piece.kind == PieceKind.INTELLECTOR and not ply.morph_into)
    else:
        __validate_capture_or_normal(ply, properties, position, allow_aura_captures)


def validate_defensor_ply(ply: Ply, properties: DerivedPlyProperties, position: "Position") -> None:
    __require(ply.departure.is_lateral_neighbour_for(ply.destination))
    if properties.ply_kind == PlyKind.SWAP:
        assert properties.target_piece
        __require(properties.target_piece.kind == PieceKind.INTELLECTOR)
    else:
        __validate_capture_or_normal(ply, properties, position)


def validate_intellector_ply(ply: Ply, properties: DerivedPlyProperties) -> None:
    __require(properties.ply_kind == PlyKind.NORMAL or properties.target_piece == Piece(PieceKind.DEFENSOR, properties.moving_piece.color))
    __require(not ply.morph_into)
    __require(ply.departure.is_lateral_neighbour_for(ply.destination))


def validate_liberator_ply(ply: Ply, properties: DerivedPlyProperties, position: "Position") -> None:
    delta_i = ply.destination.i - ply.departure.i
    delta_j = ply.destination.j - ply.departure.j
    if delta_i in (2, -2) and delta_j in (1, -1) or delta_i == 0 and delta_j in (2, -2):  # Jumps
        __validate_capture_or_normal(ply, properties, position)
    else:
        __require(properties.ply_kind == PlyKind.NORMAL)
        __require(ply.departure.is_lateral_neighbour_for(ply.destination))


def validate_aggressor_ply(ply: Ply, properties: DerivedPlyProperties, position: "Position") -> None:
    delta_i = ply.destination.i - ply.departure.i
    delta_j = ply.destination.j - ply.departure.j
    __require(delta_i)
    if delta_j == 0:
        __require(delta_i % 2 == 0)
        if abs(delta_i) >= 4:
            step = 2 if delta_i > 0 else -2
            for i in range(ply.departure.i + step, ply.destination.i, step):
                __require(not position.piece_arrangement.get(HexCoordinates(i, ply.departure.j)))
    else:
        # Using absolute directions there for convenience
        if delta_i < 0:
            if delta_j < 0:
                direction = PieceMovementDirection.AGR_FORWARD_LEFT
            else:
                direction = PieceMovementDirection.AGR_BACK_LEFT
        else:
            if delta_j < 0:
                direction = PieceMovementDirection.AGR_FORWARD_RIGHT
            else:
                direction = PieceMovementDirection.AGR_BACK_RIGHT
        __validate_raycast_reachability(ply, position, direction)
    __validate_capture_or_normal(ply, properties, position)


def validate_dominator_ply(ply: Ply, properties: DerivedPlyProperties, position: "Position") -> None:
    delta_i = ply.destination.i - ply.departure.i
    delta_j = ply.destination.j - ply.departure.j
    if delta_i == 0:
        __require(delta_j)
        if abs(delta_j) >= 2:
            step = 1 if delta_j > 0 else -1
            for j in range(ply.departure.j + step, ply.destination.j, step):
                __require(not position.piece_arrangement.get(HexCoordinates(ply.departure.i, j)))
    else:
        # Using absolute directions there for convenience
        if delta_i < 0:
            if delta_j < 0:
                direction = PieceMovementDirection.FORWARD_LEFT
            elif delta_j > 0:
                direction = PieceMovementDirection.BACK_LEFT
            elif ply.departure.i % 2 == 0:
                direction = PieceMovementDirection.BACK_LEFT
            else:
                direction = PieceMovementDirection.FORWARD_LEFT
        else:
            if delta_j < 0:
                direction = PieceMovementDirection.FORWARD_RIGHT
            elif delta_j > 0:
                direction = PieceMovementDirection.BACK_RIGHT
            elif ply.departure.i % 2 == 0:
                direction = PieceMovementDirection.BACK_RIGHT
            else:
                direction = PieceMovementDirection.FORWARD_RIGHT
        __validate_raycast_reachability(ply, position, direction)
    __validate_capture_or_normal(ply, properties, position)
