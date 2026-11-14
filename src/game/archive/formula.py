"""The game archive formula: parsing and validating the JSON tree described in knowledge/game_archive.md ("Formula format").

A formula comes in two forms. Stored formulas (saved filters, URL fragments) keep `DateTime` operands as local dates or
datetimes. Search and export requests carry them resolved into UTC instants: `{"at": <ISO 8601>, "inclusive": <bool>}`
"""
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any, Literal

from common.bots import HXCONDA
from common.time_control import TimeControlKind
from game.archive.constants import (
    FORMULA_VERSION,
    MAX_COSTLY_LEAVES,
    MAX_DEPTH,
    MAX_FORMULA_BYTES,
    MAX_LEAVES,
    MAX_NODES,
    MAX_VALUES_PER_LEAF,
)
from game.datatypes import OutcomeKind


class FormulaError(ValueError):
    pass


class Property(StrEnum):
    STARTED_AT = auto()
    ENDED_AT = auto()
    INITIAL_TIME = auto()
    BONUS_TIME = auto()
    DURATION = auto()
    TIME_LEFT = auto()
    MOVE_CNT = auto()
    ELO = auto()
    PLAYER = auto()
    TIME_CONTROL_KIND = auto()
    RATED = auto()
    OUTCOME = auto()
    STARTING_POSITION = auto()
    OPENING = auto()
    ELO_PROVISIONAL = auto()
    WINNER = auto()
    RESULT = auto()


class Operator(StrEnum):
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    EQ = auto()
    BETWEEN = auto()
    UNKNOWN = auto()


class ValueType(StrEnum):
    DATETIME = auto()
    DURATION = auto()
    INT = auto()


class ParameterType(StrEnum):
    OPTIONAL_COLOR = auto()
    PLAYER_OR_COLOR = auto()
    USER_OR_COLOR = auto()


@dataclass(frozen=True)
class OperatorPropertySpec:
    value_type: ValueType
    operators: frozenset[Operator]
    parameter: ParameterType | None = None


_DATETIME_OPERATORS = frozenset({Operator.LT, Operator.GT, Operator.BETWEEN})
_ORDER_OPERATORS = frozenset({Operator.LT, Operator.GT, Operator.LE, Operator.GE, Operator.BETWEEN})

OPERATOR_PROPERTIES: dict[Property, OperatorPropertySpec] = {
    Property.STARTED_AT: OperatorPropertySpec(ValueType.DATETIME, _DATETIME_OPERATORS | {Operator.UNKNOWN}),
    Property.ENDED_AT: OperatorPropertySpec(ValueType.DATETIME, _DATETIME_OPERATORS | {Operator.UNKNOWN}),
    Property.INITIAL_TIME: OperatorPropertySpec(ValueType.DURATION, _ORDER_OPERATORS),
    Property.BONUS_TIME: OperatorPropertySpec(ValueType.DURATION, _ORDER_OPERATORS),
    Property.DURATION: OperatorPropertySpec(ValueType.DURATION, _ORDER_OPERATORS | {Operator.UNKNOWN}),
    Property.TIME_LEFT: OperatorPropertySpec(ValueType.DURATION, _ORDER_OPERATORS | {Operator.UNKNOWN}, ParameterType.PLAYER_OR_COLOR),
    Property.MOVE_CNT: OperatorPropertySpec(ValueType.INT, _ORDER_OPERATORS | {Operator.EQ}),
    Property.ELO: OperatorPropertySpec(ValueType.INT, _ORDER_OPERATORS | {Operator.EQ}, ParameterType.USER_OR_COLOR),
}

EQUALITY_PROPERTIES: dict[Property, ParameterType | None] = {
    Property.PLAYER: ParameterType.OPTIONAL_COLOR,
    Property.TIME_CONTROL_KIND: None,
    Property.RATED: None,
    Property.OUTCOME: None,
    Property.STARTING_POSITION: None,
    Property.OPENING: None,
    Property.ELO_PROVISIONAL: ParameterType.USER_OR_COLOR,
    Property.WINNER: None,
    Property.RESULT: None,
}

COSTLY_PROPERTIES = frozenset({Property.STARTING_POSITION, Property.OPENING})

OPERAND_COUNTS: dict[Operator, int] = {
    Operator.LT: 1,
    Operator.GT: 1,
    Operator.LE: 1,
    Operator.GE: 1,
    Operator.EQ: 1,
    Operator.BETWEEN: 2,
    Operator.UNKNOWN: 0,
}

BOT_FAMILY_CODES: dict[str, str] = {
    "haxaconda_standard": "std",
    "haxaconda_trailblazer": "trl",
    "haxaconda_vrezh": "vrz",
    "haxaconda_fortress": "frt",
    "haxaconda_unchained": "unc",
}
ANACONDA_FAMILY = "anaconda"


class Color(StrEnum):
    WHITE = auto()
    BLACK = auto()


class Result(StrEnum):
    ONGOING = auto()
    WHITE_WON = auto()
    BLACK_WON = auto()
    DRAW = auto()


@dataclass(frozen=True)
class UserValue:
    login: str


@dataclass(frozen=True)
class GuestValue:
    guest_id: int


@dataclass(frozen=True)
class BotValue:
    family: str | None = None  # None: any bot
    level: int | None = None  # None: any level of the family


PlayerValue = UserValue | GuestValue | BotValue
ColorOrPlayer = Color | PlayerValue
OptionalColorValue = Color | Literal["any"]


@dataclass(frozen=True)
class SipValue:
    sip: str


StartingPositionValue = Literal["default"] | SipValue
WinnerValue = Literal["ongoing", "draw"] | PlayerValue


@dataclass(frozen=True)
class Instant:
    """A resolved `DateTime` operand of a search request"""
    at: datetime
    inclusive: bool


@dataclass(frozen=True)
class LocalDateTime:
    """A stored `DateTime` operand: a date, or a date with a time, in the viewer's wall-clock time"""
    text: str


Operand = int | Instant | LocalDateTime


@dataclass
class OperatorLeaf:
    property: Property
    parameter: Any  # ColorOrPlayer for time_left, Color | UserValue for elo, None otherwise
    operator: Operator
    operands: list[Operand]


@dataclass
class EqualityLeaf:
    property: Property
    parameter: Any  # OptionalColorValue for player, Color | UserValue for elo_provisional, None otherwise
    values: list[Any]


@dataclass
class AndNode:
    children: list[Node]


@dataclass
class OrNode:
    children: list[Node]


@dataclass
class NotNode:
    child: Node


Node = AndNode | OrNode | NotNode | OperatorLeaf | EqualityLeaf


_LOCAL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_LOGIN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def _fail(message: str) -> FormulaError:
    return FormulaError(message)


def _expect_dict(raw: Any, what: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _fail(f"{what} must be an object")
    return raw


def _expect_int(raw: Any, what: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _fail(f"{what} must be an integer")
    return raw


def _parse_color(raw: Any) -> Color:
    try:
        return Color(raw)
    except ValueError:
        raise _fail(f"Unknown color {raw!r}")


def _parse_player(raw: Any) -> PlayerValue:
    obj = _expect_dict(raw, "A player")
    if len(obj) != 1:
        raise _fail("A player has exactly one of `user`, `guest`, `bot`")
    if "user" in obj:
        login = obj["user"]
        if not isinstance(login, str) or not _LOGIN.match(login):
            raise _fail(f"Invalid login {login!r}")
        return UserValue(login)
    if "guest" in obj:
        guest_id = _expect_int(obj["guest"], "A guest id")
        if guest_id < 0:
            raise _fail("A guest id can't be negative")
        return GuestValue(guest_id)
    if "bot" in obj:
        bot = _expect_dict(obj["bot"], "A bot")
        family = bot.get("family")
        level = bot.get("level")
        if family is None:
            if level is not None:
                raise _fail("A bot level needs a family")
            return BotValue()
        if family == ANACONDA_FAMILY:
            if level is not None:
                raise _fail("Anaconda has no levels")
            return BotValue(family)
        code = BOT_FAMILY_CODES.get(family)
        if code is None:
            raise _fail(f"Unknown bot family {family!r}")
        if level is not None:
            level = _expect_int(level, "A bot level")
            max_level = HXCONDA.max_strength if code == "std" else HXCONDA.max_strength - 1
            if not HXCONDA.min_strength <= level <= max_level:
                raise _fail(f"Level {level} is out of range for {family}")
        return BotValue(family, level)
    raise _fail("A player has exactly one of `user`, `guest`, `bot`")


def _parse_parameter(raw: Any, parameter_type: ParameterType) -> Any:
    match parameter_type:
        case ParameterType.OPTIONAL_COLOR:
            if raw == "any":
                return "any"
            return _parse_color(raw)
        case ParameterType.PLAYER_OR_COLOR:
            if isinstance(raw, str):
                return _parse_color(raw)
            return _parse_player(raw)
        case ParameterType.USER_OR_COLOR:
            if isinstance(raw, str):
                return _parse_color(raw)
            player = _parse_player(raw)
            if not isinstance(player, UserValue):
                raise _fail("Only a user or a color is allowed here")
            return player


def _parse_datetime_operand(raw: Any, resolved: bool) -> Instant | LocalDateTime:
    if resolved:
        obj = _expect_dict(raw, "A resolved DateTime operand")
        at = obj.get("at")
        inclusive = obj.get("inclusive")
        if not isinstance(at, str) or not isinstance(inclusive, bool):
            raise _fail("A resolved DateTime operand is {\"at\": <ISO 8601>, \"inclusive\": <bool>}")
        try:
            moment = datetime.fromisoformat(at)
        except ValueError:
            raise _fail(f"Invalid instant {at!r}")
        if moment.tzinfo is None:
            raise _fail(f"Instant {at!r} has no timezone")
        return Instant(moment.astimezone(UTC), inclusive)

    if not isinstance(raw, str) or not (_LOCAL_DATE.match(raw) or _LOCAL_DATETIME.match(raw)):
        raise _fail(f"Invalid DateTime operand {raw!r}")
    try:
        datetime.fromisoformat(raw)
    except ValueError:
        raise _fail(f"Invalid DateTime operand {raw!r}")
    return LocalDateTime(raw)


def _parse_operand(raw: Any, value_type: ValueType, resolved: bool) -> Operand:
    match value_type:
        case ValueType.DATETIME:
            return _parse_datetime_operand(raw, resolved)
        case ValueType.DURATION:
            value = _expect_int(raw, "A duration")
            if value < 0:
                raise _fail("A duration can't be negative")
            return value
        case ValueType.INT:
            return _expect_int(raw, "An integer operand")


def _parse_equality_value(prop: Property, raw: Any) -> Any:
    match prop:
        case Property.PLAYER:
            return _parse_player(raw)
        case Property.TIME_CONTROL_KIND:
            try:
                return TimeControlKind[raw]
            except (KeyError, TypeError):
                raise _fail(f"Unknown time control kind {raw!r}")
        case Property.OUTCOME:
            try:
                return OutcomeKind[raw]
            except (KeyError, TypeError):
                raise _fail(f"Unknown outcome {raw!r}")
        case Property.RATED | Property.ELO_PROVISIONAL:
            if not isinstance(raw, bool):
                raise _fail("A boolean value is expected")
            return raw
        case Property.STARTING_POSITION:
            if raw == "default":
                return "default"
            obj = _expect_dict(raw, "A starting position")
            sip = obj.get("sip")
            if len(obj) != 1 or not isinstance(sip, str) or not 0 < len(sip) <= 127:
                raise _fail("A starting position is \"default\" or {\"sip\": <SIP>}")
            return SipValue(sip)
        case Property.OPENING:
            return _expect_int(raw, "An opening id")
        case Property.WINNER:
            if raw in ("ongoing", "draw"):
                return raw
            return _parse_player(raw)
        case Property.RESULT:
            try:
                return Result(raw)
            except ValueError:
                raise _fail(f"Unknown result {raw!r}")
    raise _fail(f"{prop} is not a sole equality property")


def _parse_property(raw_property: Any) -> Property:
    try:
        return Property(raw_property)
    except ValueError:
        raise _fail(f"Unknown property {raw_property!r}")


def _parse_leaf(obj: dict[str, Any], resolved: bool) -> OperatorLeaf | EqualityLeaf:
    prop = _parse_property(obj.get("property"))

    if prop in OPERATOR_PROPERTIES:
        spec = OPERATOR_PROPERTIES[prop]
        if set(obj) - {"property", "parameter", "operator", "operands"}:
            raise _fail(f"Unexpected fields in a {prop} condition")
        parameter = None
        if spec.parameter:
            if "parameter" not in obj:
                raise _fail(f"{prop} needs a parameter")
            parameter = _parse_parameter(obj["parameter"], spec.parameter)
        elif "parameter" in obj:
            raise _fail(f"{prop} takes no parameter")
        try:
            operator = Operator(str(obj.get("operator")))
        except ValueError:
            raise _fail(f"Unknown operator {obj.get('operator')!r}")
        if operator not in spec.operators:
            raise _fail(f"{operator} is not allowed for {prop}")
        raw_operands = obj.get("operands", [])
        if not isinstance(raw_operands, list) or len(raw_operands) != OPERAND_COUNTS[operator]:
            raise _fail(f"{operator} takes {OPERAND_COUNTS[operator]} operands")
        operands = [_parse_operand(raw, spec.value_type, resolved) for raw in raw_operands]
        return OperatorLeaf(prop, parameter, operator, operands)

    parameter_type = EQUALITY_PROPERTIES[prop]
    if set(obj) - {"property", "parameter", "values"}:
        raise _fail(f"Unexpected fields in a {prop} condition")
    parameter = None
    if parameter_type:
        if "parameter" not in obj:
            raise _fail(f"{prop} needs a parameter")
        parameter = _parse_parameter(obj["parameter"], parameter_type)
    elif "parameter" in obj:
        raise _fail(f"{prop} takes no parameter")
    raw_values = obj.get("values")
    if not isinstance(raw_values, list) or not raw_values:
        raise _fail(f"{prop} needs a non-empty list of values")
    if len(raw_values) > MAX_VALUES_PER_LEAF:
        raise _fail(f"At most {MAX_VALUES_PER_LEAF} values per condition")
    if prop in (Property.RATED, Property.ELO_PROVISIONAL) and len(raw_values) != 1:
        raise _fail(f"{prop} takes exactly one value")
    return EqualityLeaf(prop, parameter, [_parse_equality_value(prop, raw) for raw in raw_values])


@dataclass
class _Counts:
    nodes: int = 0
    leaves: int = 0
    costly: int = 0


def _parse_node(raw: Any, depth: int, counts: _Counts, resolved: bool) -> Node:
    obj = _expect_dict(raw, "A condition")
    counts.nodes += 1
    if counts.nodes > MAX_NODES:
        raise _fail(f"At most {MAX_NODES} conditions")

    for keyword in ("and", "or", "not"):
        if keyword in obj:
            if len(obj) != 1:
                raise _fail(f"A `{keyword}` condition has no other fields")
            if depth + 1 > MAX_DEPTH:
                raise _fail(f"At most {MAX_DEPTH} nested groups")
            if keyword == "not":
                return NotNode(_parse_node(obj["not"], depth + 1, counts, resolved))
            raw_children = obj[keyword]
            if not isinstance(raw_children, list):
                raise _fail(f"`{keyword}` takes a list")
            children = [_parse_node(child, depth + 1, counts, resolved) for child in raw_children]
            return AndNode(children) if keyword == "and" else OrNode(children)

    leaf = _parse_leaf(obj, resolved)
    counts.leaves += 1
    if counts.leaves > MAX_LEAVES:
        raise _fail(f"At most {MAX_LEAVES} conditions")
    if leaf.property in COSTLY_PROPERTIES:
        counts.costly += 1
        if counts.costly > MAX_COSTLY_LEAVES:
            raise _fail(f"At most {MAX_COSTLY_LEAVES} opening and starting position conditions")
    return leaf


def _check_alternation(node: Node, parent_kind: type | None) -> None:
    """A recursive condition never directly holds one of its own kind"""
    if isinstance(node, (AndNode, OrNode)):
        if type(node) is parent_kind:
            raise _fail("Nested groups must alternate")
        for child in node.children:
            _check_alternation(child, type(node))
    elif isinstance(node, NotNode):
        if parent_kind is NotNode:
            raise _fail("Nested groups must alternate")
        _check_alternation(node.child, NotNode)


def upgrade(document: dict[str, Any]) -> dict[str, Any]:
    """Brings an older formula document to the current version. Stored filters are migrated along with the DB,
    so only documents from the outside (URL fragments) ever need this"""
    version = document.get("version")
    if version == FORMULA_VERSION:
        return document
    raise _fail(f"Unsupported formula version {version!r}")


def parse_formula(document: Any, resolved: bool) -> AndNode:
    """Validates a formula document and returns its root. Raises FormulaError"""
    obj = _expect_dict(document, "A formula")
    if len(json.dumps(obj, separators=(",", ":"))) > MAX_FORMULA_BYTES:
        raise _fail(f"A formula takes at most {MAX_FORMULA_BYTES} bytes")
    obj = upgrade(obj)
    if set(obj) != {"version", "root"}:
        raise _fail("A formula has exactly `version` and `root`")
    root = _parse_node(obj["root"], 0, _Counts(), resolved)
    if not isinstance(root, AndNode):
        raise _fail("The root is an `and` condition")
    _check_alternation(root, None)
    return root
