from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto

from src.rules.coords import HexCoordinates
from src.rules.piece import Piece, PieceColor, PieceKind
from src.rules.piece_movement import PieceMovementDirection
from src.rules.ply import DerivedPlyProperties, Ply, PlyKind
from src.rules.ply_validation import (
    PlyImpossibleException,
    validate_aggressor_ply,
    validate_defensor_ply,
    validate_dominator_ply,
    validate_intellector_ply,
    validate_liberator_ply,
    validate_progressor_ply,
)


class PositionFinalityGroup(StrEnum):
    VALID_NON_FINAL = auto()
    FATUM = auto()
    BREAKTHROUGH = auto()
    INVALID = auto()


@dataclass
class PerformPlyOutput:
    performed_ply: Ply
    old_position: Position
    new_position: Position
    properties: DerivedPlyProperties

    def to_notation(self) -> str:
        return self.performed_ply.to_notation(self.old_position, self.properties)


@dataclass
class Position:
    piece_arrangement: dict[HexCoordinates, Piece] = field(default_factory=dict)
    color_to_move: PieceColor = PieceColor.WHITE

    @classmethod
    def default_starting(cls) -> Position:
        return Position(
            piece_arrangement={
                HexCoordinates(0, 0): Piece(PieceKind.DOMINATOR, PieceColor.BLACK),
                HexCoordinates(1, 0): Piece(PieceKind.LIBERATOR, PieceColor.BLACK),
                HexCoordinates(2, 0): Piece(PieceKind.AGGRESSOR, PieceColor.BLACK),
                HexCoordinates(3, 0): Piece(PieceKind.DEFENSOR, PieceColor.BLACK),
                HexCoordinates(4, 0): Piece(PieceKind.INTELLECTOR, PieceColor.BLACK),
                HexCoordinates(5, 0): Piece(PieceKind.DEFENSOR, PieceColor.BLACK),
                HexCoordinates(6, 0): Piece(PieceKind.AGGRESSOR, PieceColor.BLACK),
                HexCoordinates(7, 0): Piece(PieceKind.LIBERATOR, PieceColor.BLACK),
                HexCoordinates(8, 0): Piece(PieceKind.DOMINATOR, PieceColor.BLACK),
                HexCoordinates(0, 1): Piece(PieceKind.PROGRESSOR, PieceColor.BLACK),
                HexCoordinates(2, 1): Piece(PieceKind.PROGRESSOR, PieceColor.BLACK),
                HexCoordinates(4, 1): Piece(PieceKind.PROGRESSOR, PieceColor.BLACK),
                HexCoordinates(6, 1): Piece(PieceKind.PROGRESSOR, PieceColor.BLACK),
                HexCoordinates(8, 1): Piece(PieceKind.PROGRESSOR, PieceColor.BLACK),
                HexCoordinates(0, 5): Piece(PieceKind.PROGRESSOR, PieceColor.WHITE),
                HexCoordinates(2, 5): Piece(PieceKind.PROGRESSOR, PieceColor.WHITE),
                HexCoordinates(4, 5): Piece(PieceKind.PROGRESSOR, PieceColor.WHITE),
                HexCoordinates(6, 5): Piece(PieceKind.PROGRESSOR, PieceColor.WHITE),
                HexCoordinates(8, 5): Piece(PieceKind.PROGRESSOR, PieceColor.WHITE),
                HexCoordinates(0, 6): Piece(PieceKind.DOMINATOR, PieceColor.WHITE),
                HexCoordinates(1, 5): Piece(PieceKind.LIBERATOR, PieceColor.WHITE),
                HexCoordinates(2, 6): Piece(PieceKind.AGGRESSOR, PieceColor.WHITE),
                HexCoordinates(3, 5): Piece(PieceKind.DEFENSOR, PieceColor.WHITE),
                HexCoordinates(4, 6): Piece(PieceKind.INTELLECTOR, PieceColor.WHITE),
                HexCoordinates(5, 5): Piece(PieceKind.DEFENSOR, PieceColor.WHITE),
                HexCoordinates(6, 6): Piece(PieceKind.AGGRESSOR, PieceColor.WHITE),
                HexCoordinates(7, 5): Piece(PieceKind.LIBERATOR, PieceColor.WHITE),
                HexCoordinates(8, 6): Piece(PieceKind.DOMINATOR, PieceColor.WHITE),
            },
            color_to_move=PieceColor.WHITE
        )

    def is_valid_starting(self) -> bool:
        return self.get_finality_group() == PositionFinalityGroup.VALID_NON_FINAL

    def is_hex_under_aura(self, coordinates: HexCoordinates, aura_side: PieceColor) -> bool:
        for intellector_search_direction in PieceMovementDirection.lateral_directions():
            nearby_hex_coordinates = coordinates.step(intellector_search_direction, distance=1)
            if not nearby_hex_coordinates:
                continue
            nearby_piece = self.piece_arrangement.get(nearby_hex_coordinates)
            if nearby_piece == Piece(PieceKind.INTELLECTOR, aura_side):
                return True
        return False

    def collect_avalanche_plys(
        self,
        departure: HexCoordinates,
        directions: list[PieceMovementDirection],
        moved_piece: Piece,
        aura_active: bool
    ) -> list[Ply]:
        plys = []
        for direction in directions:
            current_coords = departure.step(direction, moved_piece.color)
            while current_coords:
                target_piece = self.piece_arrangement.get(current_coords)
                if target_piece:
                    if target_piece.color != moved_piece.color:
                        plys.append(Ply(departure, current_coords))
                        if aura_active and target_piece.kind not in (PieceKind.INTELLECTOR, moved_piece.kind):
                            plys.append(Ply(departure, current_coords, target_piece.kind))
                    break
                plys.append(Ply(departure, current_coords))
                current_coords = current_coords.step(direction, moved_piece.color)
        return plys

    def available_plys_from_hex(self, departure: HexCoordinates, pre_retrieved_moved_piece: Piece | None = None) -> list[Ply]:
        moved_piece = pre_retrieved_moved_piece or self.piece_arrangement.get(departure)
        if not moved_piece or moved_piece.color != self.color_to_move:
            return []

        aura_active = self.is_hex_under_aura(departure, moved_piece.color)

        plys = []

        match moved_piece.kind:
            case PieceKind.AGGRESSOR:
                plys = self.collect_avalanche_plys(departure, PieceMovementDirection.radial_directions(), moved_piece, aura_active)
            case PieceKind.DOMINATOR:
                plys = self.collect_avalanche_plys(departure, PieceMovementDirection.lateral_directions(), moved_piece, aura_active)
            case PieceKind.INTELLECTOR:
                for direction in PieceMovementDirection.lateral_directions():
                    destination = departure.step(direction, moved_piece.color)
                    if not destination:
                        continue
                    target_piece = self.piece_arrangement.get(destination)
                    if not target_piece or target_piece == Piece(PieceKind.DEFENSOR, moved_piece.color):
                        plys.append(Ply(departure, destination))
            case PieceKind.DEFENSOR:
                for direction in PieceMovementDirection.lateral_directions():
                    destination = departure.step(direction, moved_piece.color)
                    if not destination:
                        continue
                    target_piece = self.piece_arrangement.get(destination)
                    if not target_piece or target_piece.color != moved_piece.color or target_piece.kind == PieceKind.INTELLECTOR:
                        plys.append(Ply(departure, destination))
                        if target_piece and target_piece.color != moved_piece.color and target_piece.kind not in (PieceKind.INTELLECTOR, PieceKind.DEFENSOR) and aura_active:
                            plys.append(Ply(departure, destination, target_piece.kind))
            case PieceKind.PROGRESSOR:
                for direction in PieceMovementDirection.forward_lateral_directions():
                    destination = departure.step(direction, moved_piece.color)
                    if not destination:
                        continue
                    target_piece = self.piece_arrangement.get(destination)
                    if target_piece and target_piece.color == moved_piece.color:
                        continue
                    if destination.is_final_row_for(moved_piece.color):
                        plys += [Ply(departure, destination, promoted_piece_kind) for promoted_piece_kind in PieceKind.promotion_options()]
                    else:
                        plys.append(Ply(departure, destination))
            case PieceKind.LIBERATOR:
                for direction in PieceMovementDirection.lateral_directions():
                    destination = departure.step(direction, moved_piece.color)
                    if not destination:
                        continue
                    target_piece = self.piece_arrangement.get(destination)
                    if not target_piece:
                        plys.append(Ply(departure, destination))

                    destination = destination.step(direction, moved_piece.color)
                    if not destination:
                        continue
                    target_piece = self.piece_arrangement.get(destination)
                    if not target_piece or target_piece.color != moved_piece.color:
                        plys.append(Ply(departure, destination))
                        if target_piece and target_piece.kind not in (PieceKind.INTELLECTOR, moved_piece.kind):
                            plys.append(Ply(departure, destination, target_piece.kind))

        return plys

    def available_plys(self) -> list[Ply]:
        plys = []
        for coordinates, piece in self.piece_arrangement.items():
            plys += self.available_plys_from_hex(coordinates, piece)
        return plys

    def validate_ply(self, ply: Ply, allow_progressor_aura: bool = False, pre_check_finality: bool = False) -> DerivedPlyProperties:
        if pre_check_finality and self.get_finality_group() != PositionFinalityGroup.VALID_NON_FINAL:
            raise PlyImpossibleException

        moving_piece = self.piece_arrangement.get(ply.departure)
        if not moving_piece or moving_piece.color != self.color_to_move or not ply.destination.is_valid():
            raise PlyImpossibleException

        properties = DerivedPlyProperties.from_pieces(
            moving_piece=moving_piece,
            target_piece=self.piece_arrangement.get(ply.destination)
        )

        match moving_piece.kind:
            case PieceKind.PROGRESSOR:
                validate_progressor_ply(ply, properties, self, allow_progressor_aura)
            case PieceKind.DEFENSOR:
                validate_defensor_ply(ply, properties, self)
            case PieceKind.INTELLECTOR:
                validate_intellector_ply(ply, properties)
            case PieceKind.LIBERATOR:
                validate_liberator_ply(ply, properties, self)
            case PieceKind.AGGRESSOR:
                validate_aggressor_ply(ply, properties, self)
            case PieceKind.DOMINATOR:
                validate_dominator_ply(ply, properties, self)

        return properties

    def is_ply_possible(self, ply: Ply, allow_progressor_aura: bool = False) -> bool:
        try:
            self.validate_ply(ply, allow_progressor_aura)
        except PlyImpossibleException:
            return False
        else:
            return True

    def perform_ply(self, ply: Ply, validate: bool = False, allow_progressor_aura: bool = False, pre_check_finality: bool = False) -> PerformPlyOutput:
        if validate:
            properties = self.validate_ply(ply, allow_progressor_aura, pre_check_finality)
        else:
            properties = DerivedPlyProperties.from_pieces(
                moving_piece=self.piece_arrangement[ply.departure],
                target_piece=self.piece_arrangement.get(ply.destination)
            )

        new_arrangement = self.piece_arrangement.copy()

        if properties.ply_kind == PlyKind.SWAP:
            assert properties.target_piece
            new_arrangement[ply.departure] = properties.target_piece
            new_arrangement[ply.destination] = properties.moving_piece
        else:
            new_arrangement.pop(ply.departure, None)
            new_arrangement[ply.destination] = Piece(ply.morph_into or properties.moving_piece.kind, properties.moving_piece.color)

        return PerformPlyOutput(
            performed_ply=ply,
            old_position=self,
            new_position=Position(
                new_arrangement,
                self.color_to_move.opposite()
            ),
            properties=properties
        )

    def get_finality_group(self) -> PositionFinalityGroup:
        found_intellector_colors = set()
        has_breakthrough = False

        for coords, piece in self.piece_arrangement.items():
            if piece.kind != PieceKind.INTELLECTOR:
                continue

            if piece.color in found_intellector_colors:
                return PositionFinalityGroup.INVALID

            if coords.is_final_row_for(piece.color):
                if has_breakthrough:
                    return PositionFinalityGroup.INVALID
                has_breakthrough = True

            found_intellector_colors.add(piece.color)

        match len(found_intellector_colors):
            case 1:
                return PositionFinalityGroup.INVALID if has_breakthrough else PositionFinalityGroup.FATUM
            case 2:
                return PositionFinalityGroup.BREAKTHROUGH if has_breakthrough else PositionFinalityGroup.VALID_NON_FINAL
            case _:
                return PositionFinalityGroup.INVALID
