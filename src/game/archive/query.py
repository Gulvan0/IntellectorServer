"""SQL for game archive searches. Each property's expression is built once per request and reused by the filter,
the sorting, the result columns and the export, so that they never disagree (knowledge/game_archive.md, "Server-side evaluation")"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto
from typing import Any

from sqlalchemy import ColumnElement, and_, case, cast, exists, false, func, literal, literal_column, not_, or_, select, true
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select
from sqlalchemy.types import Integer
from sqlmodel import col

from board.opening import OpeningMapping
from common.field_types import PreciseUtcDateTime
from board.piece import PieceColor
from common.bots import HXCONDA, LEGACY_ANACONDA_NAME
from common.time_control import TimeControlKind
from game.archive.formula import (
    BOT_FAMILY_CODES,
    AndNode,
    BotValue,
    Color,
    EqualityLeaf,
    FormulaError,
    GuestValue,
    Instant,
    Node,
    NotNode,
    Operator,
    OperatorLeaf,
    OrNode,
    PlayerValue,
    Property,
    Result,
    SipValue,
    UserValue,
)
from game.models.main import Game
from game.models.outcome import GameOutcome
from game.models.ply import GamePlyEvent
from game.models.time_control import GameFischerTimeControl
from game.models.time_update import GameTimeUpdate


class SortColumn(StrEnum):
    ID = auto()
    WHITE = auto()
    BLACK = auto()
    WHITE_ELO = auto()
    BLACK_ELO = auto()
    STARTED_AT = auto()
    ENDED_AT = auto()
    DURATION = auto()
    TIME_CONTROL = auto()
    START_TIME = auto()
    BONUS_TIME = auto()
    RATED = auto()
    STARTING_POSITION = auto()
    RESULT = auto()
    OUTCOME = auto()
    OPENING = auto()
    MOVE_COUNT = auto()
    TIME_LEFT_WHITE = auto()
    TIME_LEFT_BLACK = auto()


@dataclass(frozen=True)
class SortLevel:
    column: SortColumn
    descending: bool


_LIKE_ESCAPE = "\\"


def _like_literal(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _microseconds_between(start: Any, end: Any) -> Any:
    return func.timestampdiff(literal_column("MICROSECOND"), start, end)


class ArchiveExpressions:
    """`now` is read once per request: durations and running clocks of ongoing games are taken as of it"""

    def __init__(self, now: datetime, openings: OpeningMapping) -> None:
        self.now = literal(now, PreciseUtcDateTime())  # bound as the columns are: naive UTC
        self.openings = openings
        self.latest_update = aliased(GameTimeUpdate, name="latest_update")
        self.latest_update_id = select(
            func.max(GameTimeUpdate.id)
        ).where(
            col(GameTimeUpdate.game_id) == Game.id
        ).correlate(Game).scalar_subquery()
        self.live_ply_index = GamePlyEvent.__table__.c.live_ply_index  # type: ignore[attr-defined]
        self.uses_latest_update = False  # set by the expressions reading it

    # --- the FROM clause every expression below relies on ---

    def joined_from(self, query: Select[Any]) -> Select[Any]:
        """To call once the query's expressions are built: the costly latest time update is joined only if one of them reads it"""
        query = query.select_from(
            Game
        ).outerjoin(
            GameOutcome, GameOutcome.game_id == Game.id  # type: ignore[arg-type]
        ).outerjoin(
            GameFischerTimeControl, GameFischerTimeControl.game_id == Game.id  # type: ignore[arg-type]
        )
        if not self.uses_latest_update:
            return query
        return query.outerjoin(
            self.latest_update,
            and_(self.latest_update.game_id == Game.id, self.latest_update.id == self.latest_update_id)  # type: ignore[arg-type]
        )

    # --- property expressions ---

    @property
    def is_ended(self) -> ColumnElement[bool]:
        return GameOutcome.game_id != None  # type: ignore[arg-type,return-value]  # noqa: E711

    @property
    def is_ongoing(self) -> ColumnElement[bool]:
        return GameOutcome.game_id == None  # type: ignore[arg-type,return-value]  # noqa: E711

    @property
    def started_at(self) -> Any:
        return Game.started_at

    @property
    def ended_at(self) -> Any:
        return GameOutcome.game_ended_at

    @property
    def duration_ms(self) -> Any:
        return case(
            (Game.started_at == None, None),  # type: ignore[arg-type]  # noqa: E711
            (and_(self.is_ended, GameOutcome.game_ended_at == None), None),  # type: ignore[arg-type]  # noqa: E711
            else_=func.floor(_microseconds_between(Game.started_at, func.coalesce(GameOutcome.game_ended_at, self.now)) / 1000)
        )

    @property
    def initial_time_ms(self) -> Any:
        return GameFischerTimeControl.start_seconds * 1000

    @property
    def bonus_time_ms(self) -> Any:
        return GameFischerTimeControl.increment_seconds * 1000

    @property
    def move_cnt(self) -> Any:
        return func.coalesce(
            select(
                func.max(self.live_ply_index) + 1
            ).where(
                col(GamePlyEvent.game_id) == Game.id
            ).correlate(Game).scalar_subquery(),
            0
        )

    def time_left_ms(self, color: PieceColor) -> Any:
        self.uses_latest_update = True
        update = self.latest_update
        stored = update.white_ms if color == PieceColor.WHITE else update.black_ms
        ticking = and_(update.ticking_side == color, update.updated_at != None)  # type: ignore[arg-type]  # noqa: E711
        elapsed = func.floor(_microseconds_between(update.updated_at, self.now) / 1000)
        return stored - case((ticking, elapsed), else_=0)

    def elo(self, color: PieceColor) -> Any:
        return Game.white_elo if color == PieceColor.WHITE else Game.black_elo

    def elo_provisional(self, color: PieceColor) -> Any:
        return Game.white_elo_provisional if color == PieceColor.WHITE else Game.black_elo_provisional

    def player_ref(self, color: PieceColor) -> Any:
        return Game.white_player_ref if color == PieceColor.WHITE else Game.black_player_ref

    def ref_matches(self, color: PieceColor, value: PlayerValue) -> ColumnElement[bool]:
        ref = self.player_ref(color)
        match value:
            case UserValue(login):
                return ref == login  # type: ignore[no-any-return]
            case GuestValue(guest_id):
                return ref == f"_{guest_id}"  # type: ignore[no-any-return]
            case BotValue(None, _):
                return ref.like("+%")  # type: ignore[no-any-return]
            case BotValue(family, level) if family in BOT_FAMILY_CODES:
                prefix = f"+{HXCONDA.ref_prefix}_{BOT_FAMILY_CODES[family]}_"
                if level is not None:
                    return ref == f"{prefix}{level}"  # type: ignore[no-any-return]
                return ref.like(_like_literal(prefix) + "%", escape=_LIKE_ESCAPE)  # type: ignore[no-any-return]
            case BotValue(_, _):
                return ref == f"+{LEGACY_ANACONDA_NAME}"  # type: ignore[no-any-return]
        raise FormulaError(f"Unsupported player {value!r}")

    def plays(self, value: PlayerValue) -> ColumnElement[bool]:
        return or_(self.ref_matches(PieceColor.WHITE, value), self.ref_matches(PieceColor.BLACK, value))

    def _by_player(self, value: PlayerValue, of_color: Any) -> Any:
        """The value of `of_color(color)` for the side `value` plays; null for a game it doesn't play"""
        return case(
            (self.ref_matches(PieceColor.WHITE, value), of_color(PieceColor.WHITE)),
            (self.ref_matches(PieceColor.BLACK, value), of_color(PieceColor.BLACK)),
            else_=None
        )

    def by_parameter(self, parameter: Any, of_color: Any) -> Any:
        if isinstance(parameter, Color):
            return of_color(PieceColor(parameter.value))
        return self._by_player(parameter, of_color)

    def opening_sips(self, opening_id: int) -> list[str]:
        if not 0 <= opening_id < len(self.openings.entries):
            raise FormulaError(f"Unknown opening id {opening_id}")
        entry = self.openings.entries[opening_id]
        return sorted({entry.sip, entry.other_sip})

    @property
    def opening_code(self) -> Any:
        codes: dict[str, str] = {sip: entry.code for sip, entry in self.openings.mapping.items()}
        return case(codes, value=Game.opening_sip, else_=None)

    @property
    def result_order(self) -> Any:
        return case(
            (self.is_ongoing, 0),
            (GameOutcome.winner == PieceColor.WHITE, 1),  # type: ignore[arg-type]
            (GameOutcome.winner == PieceColor.BLACK, 2),  # type: ignore[arg-type]
            else_=3
        )

    # --- conditions ---

    def _compare(self, value: Any, operator: Operator, operands: list[Any]) -> ColumnElement[bool]:
        if operator == Operator.UNKNOWN:
            return value == None  # type: ignore[no-any-return]  # noqa: E711

        if isinstance(operands[0], Instant):
            first: Instant = operands[0]
            match operator:
                case Operator.LT:
                    return value <= first.at if first.inclusive else value < first.at  # type: ignore[no-any-return]
                case Operator.GT:
                    return value >= first.at if first.inclusive else value > first.at  # type: ignore[no-any-return]
                case Operator.BETWEEN:
                    second: Instant = operands[1]
                    lower = value >= first.at if first.inclusive else value > first.at
                    upper = value <= second.at if second.inclusive else value < second.at
                    return and_(lower, upper)
            raise FormulaError(f"{operator} is not allowed for a DateTime")

        if not isinstance(operands[0], int):
            raise FormulaError("DateTime operands must be resolved into instants")

        match operator:
            case Operator.LT:
                return value < operands[0]  # type: ignore[no-any-return]
            case Operator.GT:
                return value > operands[0]  # type: ignore[no-any-return]
            case Operator.LE:
                return value <= operands[0]  # type: ignore[no-any-return]
            case Operator.GE:
                return value >= operands[0]  # type: ignore[no-any-return]
            case Operator.EQ:
                return value == operands[0]  # type: ignore[no-any-return]
            case Operator.BETWEEN:
                return and_(value >= operands[0], value <= operands[1])
        raise FormulaError(f"Unsupported operator {operator}")

    def _operator_leaf(self, leaf: OperatorLeaf) -> tuple[ColumnElement[bool], list[ColumnElement[bool]]]:
        restrictions: list[ColumnElement[bool]] = []
        not_correspondence = Game.time_control_kind != TimeControlKind.CORRESPONDENCE

        match leaf.property:
            case Property.STARTED_AT:
                value = self.started_at
            case Property.ENDED_AT:
                value = self.ended_at
                restrictions.append(self.is_ended)
            case Property.INITIAL_TIME:
                value = self.initial_time_ms
                restrictions.append(not_correspondence)  # type: ignore[arg-type]
            case Property.BONUS_TIME:
                value = self.bonus_time_ms
                restrictions.append(not_correspondence)  # type: ignore[arg-type]
            case Property.DURATION:
                value = self.duration_ms
            case Property.TIME_LEFT:
                value = self.by_parameter(leaf.parameter, self.time_left_ms)
                restrictions.append(not_correspondence)  # type: ignore[arg-type]
                if not isinstance(leaf.parameter, Color):
                    restrictions.append(self.plays(leaf.parameter))
            case Property.MOVE_CNT:
                value = self.move_cnt
            case Property.ELO:
                value = self.by_parameter(leaf.parameter, self.elo)
                restrictions.append(Game.rated == True)  # type: ignore[arg-type]  # noqa: E712
                if not isinstance(leaf.parameter, Color):
                    restrictions.append(self.plays(leaf.parameter))
            case _:
                raise FormulaError(f"{leaf.property} takes no operator")

        return self._compare(value, leaf.operator, leaf.operands), restrictions

    def _equality_leaf(self, leaf: EqualityLeaf) -> tuple[ColumnElement[bool], list[ColumnElement[bool]]]:
        restrictions: list[ColumnElement[bool]] = []

        match leaf.property:
            case Property.PLAYER:
                colors = [PieceColor.WHITE, PieceColor.BLACK] if leaf.parameter == "any" else [PieceColor(leaf.parameter.value)]
                condition = or_(*[self.ref_matches(color, value) for color in colors for value in leaf.values])
            case Property.TIME_CONTROL_KIND:
                condition = Game.time_control_kind.in_(leaf.values)  # type: ignore[attr-defined]
            case Property.RATED:
                condition = Game.rated == leaf.values[0]  # type: ignore[assignment]
            case Property.OUTCOME:
                condition = GameOutcome.kind.in_(leaf.values)  # type: ignore[attr-defined]
            case Property.STARTING_POSITION:
                options: list[ColumnElement[bool]] = []
                for value in leaf.values:
                    if isinstance(value, SipValue):
                        options.append(col(Game.custom_starting_sip) == value.sip)
                    else:
                        options.append(col(Game.custom_starting_sip) == None)  # noqa: E711
                condition = or_(*options)
            case Property.OPENING:
                sips = sorted({sip for opening_id in leaf.values for sip in self.opening_sips(opening_id)})
                condition = exists().where(
                    col(GamePlyEvent.game_id) == Game.id,
                    self.live_ply_index != None,  # noqa: E711
                    GamePlyEvent.sip_after.in_(sips)  # type: ignore[attr-defined]
                )
            case Property.ELO_PROVISIONAL:
                condition = self.by_parameter(leaf.parameter, self.elo_provisional) == leaf.values[0]
                restrictions.append(Game.rated == True)  # type: ignore[arg-type]  # noqa: E712
                if not isinstance(leaf.parameter, Color):
                    restrictions.append(self.plays(leaf.parameter))
            case Property.WINNER:
                options = []
                for value in leaf.values:
                    if value == "ongoing":
                        options.append(self.is_ongoing)
                    elif value == "draw":
                        options.append(and_(self.is_ended, GameOutcome.winner == None))  # type: ignore[arg-type]  # noqa: E711
                    else:
                        options.append(or_(
                            and_(GameOutcome.winner == PieceColor.WHITE, self.ref_matches(PieceColor.WHITE, value)),  # type: ignore[arg-type]
                            and_(GameOutcome.winner == PieceColor.BLACK, self.ref_matches(PieceColor.BLACK, value)),  # type: ignore[arg-type]
                        ))
                condition = or_(*options)
            case Property.RESULT:
                by_result: dict[Result, ColumnElement[bool]] = {
                    Result.ONGOING: self.is_ongoing,
                    Result.WHITE_WON: col(GameOutcome.winner) == PieceColor.WHITE,
                    Result.BLACK_WON: col(GameOutcome.winner) == PieceColor.BLACK,
                    Result.DRAW: and_(self.is_ended, GameOutcome.winner == None),  # type: ignore[arg-type]  # noqa: E711
                }
                condition = or_(*[by_result[value] for value in leaf.values])
            case _:
                raise FormulaError(f"{leaf.property} is not a sole equality property")

        return condition, restrictions

    def condition(self, node: Node, negated: bool = False) -> ColumnElement[bool]:
        """Negations are pushed down to the leaves, so that each leaf's implicit restrictions stay outside the
        negation: they apply even to a condition put inside a NOT block"""
        match node:
            case AndNode(children) | OrNode(children):
                conjunctive = isinstance(node, AndNode) != negated
                if not children:
                    return true() if conjunctive else false()  # type: ignore[return-value]
                parts = [self.condition(child, negated) for child in children]
                return and_(*parts) if conjunctive else or_(*parts)
            case NotNode(child):
                return self.condition(child, not negated)
            case OperatorLeaf() | EqualityLeaf():
                compiled, restrictions = self._operator_leaf(node) if isinstance(node, OperatorLeaf) else self._equality_leaf(node)
                if negated:
                    compiled = not_(compiled)
                return and_(*restrictions, compiled) if restrictions else compiled
        raise FormulaError(f"Unsupported node {node!r}")

    # --- sorting ---

    def _player_order(self, color: PieceColor) -> list[Any]:
        """Users, then guests, then bots; users by login, guests by id, bots by slug"""
        ref = self.player_ref(color)
        is_bot = ref.like("+%")
        is_guest = ref.like(_like_literal("_") + "%", escape=_LIKE_ESCAPE)
        kind = case((is_bot, 2), (is_guest, 1), else_=0)
        guest_number = case((is_guest, cast(func.substring(ref, 2), Integer)), else_=None)
        return [kind, guest_number, ref]

    def sort_keys(self, column: SortColumn) -> list[Any]:
        match column:
            case SortColumn.ID:
                return [Game.id]
            case SortColumn.WHITE:
                return self._player_order(PieceColor.WHITE)
            case SortColumn.BLACK:
                return self._player_order(PieceColor.BLACK)
            case SortColumn.WHITE_ELO:
                return [Game.white_elo]
            case SortColumn.BLACK_ELO:
                return [Game.black_elo]
            case SortColumn.STARTED_AT:
                return [Game.started_at]
            case SortColumn.ENDED_AT:
                return [GameOutcome.game_ended_at]
            case SortColumn.DURATION:
                return [self.duration_ms]
            case SortColumn.TIME_CONTROL:
                return [Game.time_control_kind]
            case SortColumn.START_TIME:
                return [GameFischerTimeControl.start_seconds]
            case SortColumn.BONUS_TIME:
                return [GameFischerTimeControl.increment_seconds]
            case SortColumn.RATED:
                return [Game.rated]
            case SortColumn.STARTING_POSITION:
                return [Game.custom_starting_sip]
            case SortColumn.RESULT:
                return [self.result_order]
            case SortColumn.OUTCOME:
                return [GameOutcome.kind]  # the enum's order puts every decisive outcome before every drawish one
            case SortColumn.OPENING:
                return [self.opening_code]
            case SortColumn.MOVE_COUNT:
                return [self.move_cnt]
            case SortColumn.TIME_LEFT_WHITE:
                return [self.time_left_ms(PieceColor.WHITE)]
            case SortColumn.TIME_LEFT_BLACK:
                return [self.time_left_ms(PieceColor.BLACK)]

    def order_by(self, levels: list[SortLevel]) -> list[Any]:
        """Missing values go last in either direction: MySQL has no NULLS LAST, so a key's nullness is sorted on first"""
        clauses: list[Any] = []
        for level in levels:
            for key in self.sort_keys(level.column):
                clauses.append(key.is_(None))
                clauses.append(key.desc() if level.descending else key.asc())
        if not any(level.column == SortColumn.ID for level in levels):
            clauses.append(Game.id.desc())  # type: ignore[union-attr]
        return clauses

    # --- the result rows ---

    def row_columns(self) -> list[Any]:
        return [
            Game.id.label("id"),  # type: ignore[union-attr]
            Game.white_player_ref.label("white_ref"),  # type: ignore[attr-defined]
            Game.black_player_ref.label("black_ref"),  # type: ignore[attr-defined]
            Game.white_elo.label("white_elo"),  # type: ignore[union-attr]
            Game.white_elo_provisional.label("white_elo_provisional"),  # type: ignore[union-attr]
            Game.black_elo.label("black_elo"),  # type: ignore[union-attr]
            Game.black_elo_provisional.label("black_elo_provisional"),  # type: ignore[union-attr]
            Game.started_at.label("started_at"),  # type: ignore[union-attr]
            GameOutcome.game_ended_at.label("ended_at"),  # type: ignore[union-attr]
            self.duration_ms.label("duration_ms"),
            Game.time_control_kind.label("time_control_kind"),  # type: ignore[attr-defined]
            GameFischerTimeControl.start_seconds.label("start_seconds"),  # type: ignore[attr-defined]
            GameFischerTimeControl.increment_seconds.label("increment_seconds"),  # type: ignore[attr-defined]
            Game.rated.label("rated"),  # type: ignore[attr-defined]
            Game.custom_starting_sip.label("custom_starting_sip"),  # type: ignore[union-attr]
            Game.opening_sip.label("opening_sip"),  # type: ignore[attr-defined]
            self.is_ended.label("ended"),
            GameOutcome.kind.label("outcome_kind"),  # type: ignore[attr-defined]
            GameOutcome.winner.label("winner"),  # type: ignore[union-attr]
            self.move_cnt.label("move_count"),
            case((col(Game.time_control_kind) == TimeControlKind.CORRESPONDENCE, None), else_=self.time_left_ms(PieceColor.WHITE)).label("white_time_left_ms"),
            case((col(Game.time_control_kind) == TimeControlKind.CORRESPONDENCE, None), else_=self.time_left_ms(PieceColor.BLACK)).label("black_time_left_ms"),
        ]
