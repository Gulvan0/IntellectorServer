from __future__ import annotations

from dataclasses import dataclass, field
from enum import auto, Enum, StrEnum

import typing as tp


class PieceMovementDirection(Enum):
    FORWARD = auto()
    FORWARD_LEFT = auto()
    FORWARD_RIGHT = auto()
    BACK = auto()
    BACK_LEFT = auto()
    BACK_RIGHT = auto()
    AGR_FORWARD_LEFT = auto()
    AGR_FORWARD_RIGHT = auto()
    AGR_BACK_LEFT = auto()
    AGR_BACK_RIGHT = auto()
    AGR_LEFT = auto()
    AGR_RIGHT = auto()

    @classmethod
    def forward_lateral_directions(cls) -> list[PieceMovementDirection]:
        return [cls.FORWARD, cls.FORWARD_LEFT, cls.FORWARD_RIGHT]

    @classmethod
    def backward_lateral_directions(cls) -> list[PieceMovementDirection]:
        return [cls.BACK, cls.BACK_LEFT, cls.BACK_RIGHT]

    @classmethod
    def lateral_directions(cls) -> list[PieceMovementDirection]:
        return cls.forward_lateral_directions() + cls.backward_lateral_directions()

    @classmethod
    def radial_directions(cls) -> list[PieceMovementDirection]:
        return [cls.AGR_FORWARD_LEFT, cls.AGR_FORWARD_RIGHT, cls.AGR_BACK_LEFT, cls.AGR_BACK_RIGHT, cls.AGR_LEFT, cls.AGR_RIGHT]


class UnlimitedPieceMovementDistance:
    pass


@dataclass
class PieceMovementRule:
    allowed_directions: list[PieceMovementDirection]
    allowed_distances: list[int] | UnlimitedPieceMovementDistance
    can_capture: bool = True
    can_jump: bool = False
    swappable_with: list[PieceKind] = field(default_factory=list)


class PieceKind(StrEnum):
    PROGRESSOR = "r"
    AGGRESSOR = "g"
    DEFENSOR = "e"
    LIBERATOR = "i"
    DOMINATOR = "o"
    INTELLECTOR = "n"

    @classmethod
    def promotion_options(cls) -> list[PieceKind]:
        return [
            PieceKind.AGGRESSOR,
            PieceKind.DEFENSOR,
            PieceKind.LIBERATOR,
            PieceKind.DOMINATOR,
        ]

    @classmethod
    def affected_by_aura(cls) -> list[PieceKind]:
        return [
            PieceKind.AGGRESSOR,
            PieceKind.DEFENSOR,
            PieceKind.LIBERATOR,
            PieceKind.DOMINATOR,
        ]

    def get_movement_rules(self) -> list[PieceMovementRule]:
        match self:
            case PieceKind.PROGRESSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.forward_lateral_directions(),
                        allowed_distances=[1]
                    )
                ]
            case PieceKind.AGGRESSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.radial_directions(),
                        allowed_distances=UnlimitedPieceMovementDistance()
                    )
                ]
            case PieceKind.DEFENSOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        swappable_with=[PieceKind.INTELLECTOR]
                    )
                ]
            case PieceKind.LIBERATOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        can_capture=False
                    ),
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[2],
                        can_jump=True
                    )
                ]
            case PieceKind.DOMINATOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=UnlimitedPieceMovementDistance()
                    )
                ]
            case PieceKind.INTELLECTOR:
                return [
                    PieceMovementRule(
                        allowed_directions=PieceMovementDirection.lateral_directions(),
                        allowed_distances=[1],
                        swappable_with=[PieceKind.DEFENSOR]
                    )
                ]


class PieceColor(StrEnum):
    WHITE = "w"
    BLACK = "b"

    def opposite(self) -> PieceColor:
        return PieceColor.BLACK if self == PieceColor.WHITE else PieceColor.WHITE


@dataclass(frozen=True)
class Piece:
    kind: PieceKind
    color: PieceColor


BOARD_HEX_COUNT = 59


@dataclass(frozen=True)
class HexCoordinates:
    i: int
    j: int

    @classmethod
    def from_scalar(cls, scalar: int) -> HexCoordinates:
        i = scalar % 9 * 2
        if i > 8:
            i -= 9
        return HexCoordinates(i, scalar // 9)

    def __hash__(self) -> int:
        return self.scalar

    @property
    def scalar(self) -> int:
        base = 9 * self.j + self.i // 2
        if self.i % 2:
            return base + 5
        return base

    def is_valid(self) -> bool:
        if self.j == 6:
            return self.i % 2 == 0
        return 0 <= self.j < 6 and 0 <= self.i < 9

    def is_final_row_for(self, side: PieceColor) -> bool:
        if side == PieceColor.WHITE:
            return self.scalar < 5
        else:
            return BOARD_HEX_COUNT - 5 <= self.scalar

    def step(self, direction: PieceMovementDirection, color: PieceColor = PieceColor.WHITE, distance: int = 1) -> HexCoordinates | None:
        color_sign = 1 if color == PieceColor.WHITE else -1
        match direction:
            case PieceMovementDirection.FORWARD:
                next_hex = HexCoordinates(self.i, self.j - distance * color_sign)
            case PieceMovementDirection.FORWARD_LEFT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i - distance * color_sign, self.j - color_sign * (distance + addend) // 2)
            case PieceMovementDirection.FORWARD_RIGHT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i + distance * color_sign, self.j - color_sign * (distance + addend) // 2)
            case PieceMovementDirection.BACK:
                next_hex = HexCoordinates(self.i, self.j + distance * color_sign)
            case PieceMovementDirection.BACK_LEFT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i - distance * color_sign, self.j + color_sign * (distance + addend) // 2)
            case PieceMovementDirection.BACK_RIGHT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i + distance * color_sign, self.j + color_sign * (distance + addend) // 2)
            case PieceMovementDirection.AGR_LEFT:
                next_hex = HexCoordinates(self.i - 2 * color_sign * distance, self.j)
            case PieceMovementDirection.AGR_RIGHT:
                next_hex = HexCoordinates(self.i + 2 * color_sign * distance, self.j)
            case PieceMovementDirection.AGR_BACK_LEFT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i - distance * color_sign, self.j + color_sign * ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_BACK_RIGHT:
                addend = int(self.i % 2 == 1)
                next_hex = HexCoordinates(self.i + distance * color_sign, self.j + color_sign * ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_FORWARD_LEFT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i - distance * color_sign, self.j - color_sign * ((distance + addend) // 2 + distance))
            case PieceMovementDirection.AGR_FORWARD_RIGHT:
                addend = int(self.i % 2 == 0)
                next_hex = HexCoordinates(self.i + distance * color_sign, self.j - color_sign * ((distance + addend) // 2 + distance))
            case _:
                tp.assert_never(direction)
        return next_hex if next_hex.is_valid() else None


@dataclass
class Ply:
    departure: HexCoordinates
    destination: HexCoordinates
    morph_into: PieceKind | None = None


class PlyKind(Enum):
    NORMAL = auto()
    CAPTURE = auto()
    SWAP = auto()


@dataclass
class SuccessfulPlyResult:
    updated_position: Position
    winner: PieceColor | None
    moved_piece: Piece
    target_piece: Piece | None

    @property
    def performed_ply_kind(self) -> PlyKind:
        if not self.target_piece:
            return PlyKind.NORMAL
        if self.target_piece.color == self.moved_piece.color:
            return PlyKind.SWAP
        return PlyKind.CAPTURE


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

    @classmethod
    def from_sip(cls, sip: str) -> Position:
        position = Position()
        parts = sip.split('!', 2)

        if len(parts) == 2:
            version = 1
        else:
            version = int(parts.pop(0))

        match version:
            case 1:
                position.color_to_move = PieceColor(parts[0][0])
                parts[0] = parts[0][1:]
                for color, part in zip(PieceColor, parts):
                    for i in range(0, len(part), 2):
                        scalar_coord = ord(part[i]) - 64
                        hex_coords = HexCoordinates.from_scalar(scalar_coord)
                        piece_kind = PieceKind(part[i+1])
                        position.piece_arrangement[hex_coords] = Piece(piece_kind, color)
            case 2:
                position.color_to_move = PieceColor(parts[0][0])
                parts[0] = parts[0][1:]
                for color, part in zip(PieceColor, parts):
                    for i in range(0, len(part), 2):
                        coords_char_code = ord(part[i])
                        if coords_char_code >= 97:
                            scalar_coord = 26 + coords_char_code - 97
                        elif coords_char_code >= 65:
                            scalar_coord = coords_char_code - 65
                        else:
                            scalar_coord = 52 + coords_char_code - 48
                        hex_coords = HexCoordinates.from_scalar(scalar_coord)
                        piece_kind = PieceKind(part[i+1])
                        position.piece_arrangement[hex_coords] = Piece(piece_kind, color)
            case _:
                raise ValueError(f'Unknown version: {version}')

        return position

    def to_sip(self) -> str:
        pieces = {PieceColor.WHITE: [], PieceColor.BLACK: []}
        for hex_coords, piece in self.piece_arrangement.items():
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
                arrangement_strings[color] += chr(starting_ascii_index + scalar_coord % 26) + piece_kind.value

        return f"2!{self.color_to_move.value}{arrangement_strings[PieceColor.WHITE]}!{arrangement_strings[PieceColor.BLACK]}"

    def is_valid_starting(self) -> bool:
        found_intellector_colors = set()
        for coords, piece in self.piece_arrangement.items():
            if piece.kind != PieceKind.INTELLECTOR:
                continue
            if piece.color in found_intellector_colors or coords.is_final_row_for(piece.color):
                return False
            found_intellector_colors.add(piece.color)
        return len(found_intellector_colors) == 2

    def is_hex_under_aura(self, coordinates: HexCoordinates, aura_side: PieceColor) -> bool:
        for intellector_search_direction in PieceMovementDirection.lateral_directions():
            nearby_hex_coordinates = coordinates.step(intellector_search_direction, distance=1)
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

    def is_ply_possible(self, ply: Ply) -> bool:
        return ply in self.available_plys_from_hex(ply.departure)

    def available_plys(self) -> list[Ply]:
        plys = []
        for coordinates, piece in self.piece_arrangement.items():
            plys += self.available_plys_from_hex(coordinates, piece)
        return plys


DEFAULT_STARTING_SIP = Position.default_starting().to_sip()
