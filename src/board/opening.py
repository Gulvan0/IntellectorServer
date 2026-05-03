from dataclasses import asdict, dataclass, field

from board.coords import HexCoordinates
from board.ply import Ply
from board.position import Position
from board.serializers.sip import get_sip


@dataclass
class Entry:
    code: str
    sip: str
    other_sip: str
    name_en: str
    name_ru: str


@dataclass
class OpeningMapping:
    mapping: dict[str, Entry] = field(default_factory=dict)

    def save(self, position: Position, code: str, name_en: str, name_ru: str) -> None:
        sip = get_sip(position)
        other_sip = mirrored_sip(position)
        entry = Entry(code, sip, other_sip, name_en, name_ru)
        self.mapping[sip] = entry
        self.mapping[other_sip] = entry

    def dump(self) -> dict[str, dict[str, str]]:
        return {
            key: asdict(value)
            for key, value in self.mapping.items()
        }


def hex_coords_from_text(notation: str) -> HexCoordinates:
    i = ord(notation[0]) - ord('a')
    height = 7 if i % 2 == 0 else 6
    j = height - int(notation[1])
    assert 0 <= i <= 8
    assert 0 <= j <= 6
    return HexCoordinates(i, j)


def mirrored_hex(coords: HexCoordinates) -> HexCoordinates:
    return HexCoordinates(8 - coords.i, coords.j)


def mirrored_sip(position: Position) -> str:
    mirrored_arrangement = {}
    for hex_coords, piece in position.piece_arrangement.items():
        mirrored_arrangement[mirrored_hex(hex_coords)] = piece
    mirrored_position = Position(mirrored_arrangement, position.color_to_move)
    return get_sip(mirrored_position)


def proceed(orig_position: Position, hex_from: str, hex_to: str, morph: bool = False) -> Position:
    departure = hex_coords_from_text(hex_from)
    destination = hex_coords_from_text(hex_to)
    morph_into = orig_position.piece_arrangement[destination].kind if morph else None
    return orig_position.perform_ply(Ply(
        departure,
        destination,
        morph_into
    )).new_position


def generate_mapping() -> OpeningMapping:
    mapping = OpeningMapping()

    starting_position = Position.default_starting()
    mapping.save(starting_position, "", "Starting Position", "Начальная расстановка")

    mapping.save(proceed(starting_position, "e1", "d1"), "U0", "Verto Opening", "Дебют верто")
    mapping.save(proceed(starting_position, "d1", "d2"), "D0", "Defensor Opening", "Дебют дефенсора")

    jump = proceed(starting_position, "h1", "h3")
    mapping.save(jump, "L1", "Jump Opening", "Прыжковый дебют")

    mapping.save(proceed(jump, "i6", "i5"), "L1", "Spike Defense", "Защита шипа")

    mapping.save(proceed(starting_position, "h1", "h2"), "L2", "Passive Liberator Opening", "Дебют пассивного либератора")
    mapping.save(proceed(starting_position, "h1", "f2"), "L3", "Central Liberator Opening", "Дебют центрального либератора")

    central_prog = proceed(starting_position, "e2", "e3")
    mapping.save(central_prog, "P1", "Central Advancement", "Центральное продвижение")

    double_central_prog = proceed(central_prog, "e6", "e5")
    mapping.save(double_central_prog, "P1", "Symmetric Central Advancement", "Двойное центральное продвижение")

    bongcloud = proceed(double_central_prog, "e1", "e2")
    mapping.save(bongcloud, "P1", "Central Opening", "Центральный дебют")

    dobule_bongcloud = proceed(bongcloud, "e7", "e6")
    mapping.save(dobule_bongcloud, "P1", "Symmetric Central Opening", "Двойной центральный дебют")

    mapping.save(proceed(starting_position, "e2", "d2"), "P2", "Open Intellector Opening", "Дебют вскрытого интеллектора")
    mapping.save(proceed(starting_position, "c2", "d2"), "P3", "Inward Progressor Opening", "Центростремительный дебют прогрессора")
    mapping.save(proceed(starting_position, "c2", "b2"), "P4", "Outward Progressor Opening", "Центробежный дебют прогрессора")
    mapping.save(proceed(starting_position, "c2", "c3"), "P5", "Forward Progressor Opening", "Прямой дебют прогрессора")
    mapping.save(proceed(starting_position, "a2", "b2"), "P6", "Channel Opening", "Дебют канала")

    mapping.save(proceed(starting_position, "c1", "b2"), "A1", "Pulsum Opening", "Дебют пульсума")
    mapping.save(proceed(starting_position, "c1", "a4"), "U1", "a4/i4 Sac", "Жертва на a4/i4")
    mapping.save(proceed(starting_position, "c1", "d2"), "A2", "Central Aggressor Opening", "Дебют центрального агрессора")
    mapping.save(proceed(starting_position, "c1", "e4"), "U2", "Central Aggressor Opening", "Дебют центрального агрессора")
    mapping.save(proceed(starting_position, "c1", "f5"), "U3", "e4 Sac", "Жертва на e4")

    exchange = proceed(starting_position, "c1", "g7")
    mapping.save(exchange, "A3", "Exchange Opening", "Разменный дебют")

    non_morph = proceed(exchange, "f6", "g7")
    mapping.save(non_morph, "A31", "Exchange Opening: Capture Variant", "Разменный дебют: Вариант без превращения")

    morph = proceed(exchange, "f6", "g7", morph=True)
    mapping.save(morph, "A32", "Exchange Opening: Morph Variant", "Разменный дебют: Вариант с превращением")

    return mapping
