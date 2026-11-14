"""The XLSX export of a game archive search (knowledge/game_archive.md, "Result presentation").
Datetimes and durations are native Excel values; datetimes are written in the viewer's timezone, since Excel's have none"""
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import xlsxwriter  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlmodel import col

from board.coords import HexCoordinates
from board.deserializers.sip import position_from_sip
from board.opening import OpeningMapping
from board.piece import PieceColor
from board.ply import Ply
from board.position import Position
from board.serializers.notation import write_ply
from common.bots import LEGACY_ANACONDA_NAME, registered_bot_display_name
from common.user_ref import UserReference
from game.archive.constants import GAME_ID_PLACEHOLDER
from game.archive.formula import AndNode
from game.archive.methods import filtered_query, stream_archive_rows, translated_timeouts, with_time_limit
from game.archive.models import ArchiveColumn, ArchiveGameRow
from game.archive.query import ArchiveExpressions, SortLevel
from game.datatypes import OutcomeKind
from game.models.ply import GamePlyEvent
from net.utils.rest_error import RestErrorCode, RestException
from utils.async_orm_session import AsyncSession


MS_PER_DAY = 24 * 60 * 60 * 1000
MS_PER_HOUR = 60 * 60 * 1000
DAYS_FORMAT_LIMIT_MS = 5 * MS_PER_DAY  # where the table switches to whole days
DATETIME_TEXT_LENGTH = len("dd.mm.yyyy hh:mm:ss")
MIN_COLUMN_WIDTH = 6
MAX_COLUMN_WIDTH = 60
COLUMN_PADDING = 2
HEADER_WIDTH_FACTOR = 1.1  # bold text is wider


@dataclass(frozen=True)
class ExportTexts:
    columns: dict[ArchiveColumn, str]
    move: str  # "Move [0]"
    yes: str
    no: str
    default_position: str
    guest: str  # "Guest [0]"
    results: dict[str, str]  # ongoing, white_won, black_won, draw
    colors: dict[PieceColor, str]
    outcomes: dict[OutcomeKind, str]  # [1] is the loser's color


_EN = ExportTexts(
    columns={
        ArchiveColumn.ID: "ID",
        ArchiveColumn.LINK: "Link",
        ArchiveColumn.WHITE: "White",
        ArchiveColumn.BLACK: "Black",
        ArchiveColumn.WHITE_ELO: "White ELO",
        ArchiveColumn.BLACK_ELO: "Black ELO",
        ArchiveColumn.STARTED_AT: "Started at",
        ArchiveColumn.ENDED_AT: "Ended at",
        ArchiveColumn.DURATION: "Duration",
        ArchiveColumn.TIME_CONTROL: "Time control",
        ArchiveColumn.START_TIME: "Start time",
        ArchiveColumn.BONUS_TIME: "Bonus time",
        ArchiveColumn.RATED: "Rated",
        ArchiveColumn.STARTING_POSITION: "Starting position",
        ArchiveColumn.RESULT: "Result",
        ArchiveColumn.OUTCOME: "Outcome",
        ArchiveColumn.OPENING: "Opening",
        ArchiveColumn.MOVE_COUNT: "Move count",
        ArchiveColumn.TIME_LEFT_WHITE: "Time left (White)",
        ArchiveColumn.TIME_LEFT_BLACK: "Time left (Black)",
    },
    move="Move [0]",
    yes="Yes",
    no="No",
    default_position="Default",
    guest="Guest [0]",
    results={"ongoing": "Still ongoing", "white_won": "White won", "black_won": "Black won", "draw": "Draw"},
    colors={PieceColor.WHITE: "White", PieceColor.BLACK: "Black"},
    outcomes={
        OutcomeKind.FATUM: "Fatum",
        OutcomeKind.BREAKTHROUGH: "Breakthrough",
        OutcomeKind.STALEMATE: "Stalemate",
        OutcomeKind.TIMEOUT: "[1] lost on time",
        OutcomeKind.RESIGN: "[1] resigned",
        OutcomeKind.ABANDON: "[1] left the game",
        OutcomeKind.CHEATING_ABORT: "[1] was found cheating",
        OutcomeKind.DRAW_AGREEMENT: "By agreement",
        OutcomeKind.REPETITION: "Threefold repetition",
        OutcomeKind.NO_PROGRESS: "Sixty-move rule",
        OutcomeKind.ABORT: "Aborted",
    },
)

_RU = ExportTexts(
    columns={
        ArchiveColumn.ID: "ID",
        ArchiveColumn.LINK: "Ссылка",
        ArchiveColumn.WHITE: "Белые",
        ArchiveColumn.BLACK: "Чёрные",
        ArchiveColumn.WHITE_ELO: "ELO белых",
        ArchiveColumn.BLACK_ELO: "ELO чёрных",
        ArchiveColumn.STARTED_AT: "Начало",
        ArchiveColumn.ENDED_AT: "Окончание",
        ArchiveColumn.DURATION: "Длительность",
        ArchiveColumn.TIME_CONTROL: "Контроль времени",
        ArchiveColumn.START_TIME: "Начальное время",
        ArchiveColumn.BONUS_TIME: "Добавка",
        ArchiveColumn.RATED: "Рейтинговая",
        ArchiveColumn.STARTING_POSITION: "Начальная позиция",
        ArchiveColumn.RESULT: "Результат",
        ArchiveColumn.OUTCOME: "Исход",
        ArchiveColumn.OPENING: "Дебют",
        ArchiveColumn.MOVE_COUNT: "Число ходов",
        ArchiveColumn.TIME_LEFT_WHITE: "Остаток времени (белые)",
        ArchiveColumn.TIME_LEFT_BLACK: "Остаток времени (чёрные)",
    },
    move="Ход [0]",
    yes="Да",
    no="Нет",
    default_position="Стандартная",
    guest="Гость [0]",
    results={"ongoing": "Идёт партия", "white_won": "Победа белых", "black_won": "Победа чёрных", "draw": "Ничья"},
    colors={PieceColor.WHITE: "Белые", PieceColor.BLACK: "Чёрные"},
    outcomes={
        OutcomeKind.FATUM: "Фатум",
        OutcomeKind.BREAKTHROUGH: "Прорыв",
        OutcomeKind.STALEMATE: "Пат",
        OutcomeKind.TIMEOUT: "[1] просрочили время",
        OutcomeKind.RESIGN: "[1] сдались",
        OutcomeKind.ABANDON: "[1] покинули игру",
        OutcomeKind.CHEATING_ABORT: "[1] нарушили правила",
        OutcomeKind.DRAW_AGREEMENT: "По соглашению",
        OutcomeKind.REPETITION: "Троекратное повторение",
        OutcomeKind.NO_PROGRESS: "Правило 60 ходов",
        OutcomeKind.ABORT: "Партия прервана",
    },
)

_TIME_CONTROL_NAMES = {
    "en": {"hyperbullet": "Hyperbullet", "bullet": "Bullet", "blitz": "Blitz", "rapid": "Rapid", "classic": "Classic", "correspondence": "Correspondence"},
    "ru": {"hyperbullet": "Hyperbullet", "bullet": "Bullet", "blitz": "Blitz", "rapid": "Rapid", "classic": "Classic", "correspondence": "По переписке"},
}


def texts_for(locale: str) -> tuple[ExportTexts, dict[str, str]]:
    key = "ru" if locale.lower().startswith("ru") else "en"
    return (_RU if key == "ru" else _EN), _TIME_CONTROL_NAMES[key]


def zone_for(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise RestException(RestErrorCode.INVALID_FORMULA, f"Unknown timezone {timezone!r}")


def player_name(ref: str, nickname: str, texts: ExportTexts) -> str:
    ref_object = UserReference(ref)
    if ref_object.is_guest():
        return texts.guest.replace("[0]", str(ref_object.guest_id))
    if ref_object.is_bot():
        if ref_object.bot_name == LEGACY_ANACONDA_NAME:
            return LEGACY_ANACONDA_NAME
        return registered_bot_display_name(ref_object.bot_name) or ref_object.bot_name
    return nickname


def result_key(row: ArchiveGameRow) -> str:
    if not row.ended:
        return "ongoing"
    if row.winner == PieceColor.WHITE:
        return "white_won"
    if row.winner == PieceColor.BLACK:
        return "black_won"
    return "draw"


def outcome_text(row: ArchiveGameRow, texts: ExportTexts) -> str | None:
    if row.outcome_kind is None:
        return None
    loser = row.winner.opposite() if row.winner is not None else None
    text = texts.outcomes[row.outcome_kind]
    return text.replace("[1]", texts.colors[loser]) if loser is not None else text


class _Formats:
    def __init__(self, workbook: Any) -> None:
        self.header = workbook.add_format({"bold": True})
        self.datetime = workbook.add_format({"num_format": "dd.mm.yyyy hh:mm:ss"})
        # as the result table shows durations: the leading zero components stripped down to M:SS
        self.minutes = workbook.add_format({"num_format": "[m]:ss"})
        self.hours = workbook.add_format({"num_format": "[h]:mm:ss"})
        self.days = workbook.add_format({"num_format": "d:hh:mm:ss"})  # day of the month, so below 32 days only
        self.elo = workbook.add_format({"num_format": "0"})
        self.provisional_elo = workbook.add_format({"num_format": '0"?"'})


CellWriter = Callable[[Any, int, int, ArchiveGameRow], None]


class _MeasuredSheet:
    """A worksheet that remembers each column's widest displayed text, to size the columns once written.
    Excel's own autofit can't run on a file written in constant memory mode."""

    def __init__(self, sheet: Any, formats: _Formats) -> None:
        self.sheet = sheet
        self.formats = formats
        self.widths: dict[int, float] = {}

    def _note(self, col: int, length: float) -> None:
        self.widths[col] = max(self.widths.get(col, 0), length)

    def write_string(self, row: int, col: int, text: str, cell_format: Any = None) -> None:
        self.sheet.write_string(row, col, text, cell_format)
        self._note(col, len(text) * (HEADER_WIDTH_FACTOR if cell_format is self.formats.header else 1))

    def write_url(self, row: int, col: int, url: str) -> None:
        self.sheet.write_url(row, col, url)
        self._note(col, len(url))

    def write_datetime(self, row: int, col: int, value: datetime, cell_format: Any) -> None:
        self.sheet.write_datetime(row, col, value, cell_format)
        self._note(col, DATETIME_TEXT_LENGTH)

    def write_number(self, row: int, col: int, value: float, cell_format: Any = None) -> None:
        self.sheet.write_number(row, col, value, cell_format)
        if cell_format is self.formats.minutes:
            text = f"{int(value * 24 * 60)}:00"
        elif cell_format is self.formats.hours:
            text = f"{int(value * 24)}:00:00"
        elif cell_format is self.formats.days:
            text = "0:00:00:00"
        elif cell_format is self.formats.provisional_elo:
            text = f"{value:.0f}?"
        else:
            text = f"{value:g}"
        self._note(col, len(text))

    def fit_columns(self) -> None:
        for column_index, length in self.widths.items():
            self.sheet.set_column(column_index, column_index, min(MAX_COLUMN_WIDTH, max(MIN_COLUMN_WIDTH, length + COLUMN_PADDING)))


class _RowWriter:
    def __init__(self, workbook: Any, openings: OpeningMapping, game_url_template: str, locale: str, timezone: str) -> None:
        self.formats = _Formats(workbook)
        self.game_url_template = game_url_template
        self.openings = openings
        self.russian = locale.lower().startswith("ru")
        self.texts, self.time_control_names = texts_for(locale)
        self.zone = zone_for(timezone)

    def _datetime(self, sheet: Any, row: int, col: int, value: datetime | None) -> None:
        if value is not None:
            sheet.write_datetime(row, col, value.astimezone(self.zone).replace(tzinfo=None), self.formats.datetime)

    def _duration(self, sheet: Any, row: int, col: int, ms: int | None) -> None:
        if ms is None:
            return
        whole_ms = ms // 1000 * 1000  # whole seconds, as the table shows them
        if whole_ms < MS_PER_HOUR:
            cell_format = self.formats.minutes
        elif whole_ms < MS_PER_DAY or whole_ms >= DAYS_FORMAT_LIMIT_MS:
            cell_format = self.formats.hours
        else:
            cell_format = self.formats.days
        sheet.write_number(row, col, whole_ms / MS_PER_DAY, cell_format)

    def _elo(self, sheet: Any, row: int, col: int, elo: Any) -> None:
        if elo is not None:
            sheet.write_number(row, col, elo.elo, self.formats.provisional_elo if elo.provisional else self.formats.elo)

    def write(self, sheet: Any, row: int, col: int, column: ArchiveColumn, game: ArchiveGameRow) -> None:
        texts = self.texts
        match column:
            case ArchiveColumn.ID:
                sheet.write_number(row, col, game.id)
            case ArchiveColumn.LINK:
                sheet.write_url(row, col, self.game_url_template.replace(GAME_ID_PLACEHOLDER, str(game.id)))
            case ArchiveColumn.WHITE:
                sheet.write_string(row, col, player_name(game.white_player.user_ref, game.white_player.nickname, texts))
            case ArchiveColumn.BLACK:
                sheet.write_string(row, col, player_name(game.black_player.user_ref, game.black_player.nickname, texts))
            case ArchiveColumn.WHITE_ELO:
                self._elo(sheet, row, col, game.white_rating)
            case ArchiveColumn.BLACK_ELO:
                self._elo(sheet, row, col, game.black_rating)
            case ArchiveColumn.STARTED_AT:
                self._datetime(sheet, row, col, game.started_at)
            case ArchiveColumn.ENDED_AT:
                self._datetime(sheet, row, col, game.ended_at)
            case ArchiveColumn.DURATION:
                self._duration(sheet, row, col, game.duration_ms)
            case ArchiveColumn.TIME_CONTROL:
                sheet.write_string(row, col, self.time_control_names[game.time_control_kind.value])
            case ArchiveColumn.START_TIME:
                self._duration(sheet, row, col, game.start_seconds * 1000 if game.start_seconds is not None else None)
            case ArchiveColumn.BONUS_TIME:
                self._duration(sheet, row, col, game.increment_seconds * 1000 if game.increment_seconds is not None else None)
            case ArchiveColumn.RATED:
                sheet.write_string(row, col, texts.yes if game.rated else texts.no)
            case ArchiveColumn.STARTING_POSITION:
                sheet.write_string(row, col, game.custom_starting_sip or texts.default_position)
            case ArchiveColumn.RESULT:
                sheet.write_string(row, col, texts.results[result_key(game)])
            case ArchiveColumn.OUTCOME:
                outcome = outcome_text(game, texts)
                if outcome is not None:
                    sheet.write_string(row, col, outcome)
            case ArchiveColumn.OPENING:
                if game.opening_id is not None:
                    entry = self.openings.entries[game.opening_id]
                    sheet.write_string(row, col, entry.name_ru if self.russian else entry.name_en)
            case ArchiveColumn.MOVE_COUNT:
                sheet.write_number(row, col, game.move_count)
            case ArchiveColumn.TIME_LEFT_WHITE:
                self._duration(sheet, row, col, game.white_time_left_ms)
            case ArchiveColumn.TIME_LEFT_BLACK:
                self._duration(sheet, row, col, game.black_time_left_ms)


async def _max_move_count(session: AsyncSession, openings: OpeningMapping, root: AndNode, timeout_ms: int) -> int:
    expressions = ArchiveExpressions(datetime.now(UTC), openings)
    query = with_time_limit(filtered_query(expressions, root, [func.max(expressions.move_cnt)]), timeout_ms)
    with translated_timeouts():
        return int((await session.execute(query)).scalar_one() or 0)


async def _notations(session: AsyncSession, games: list[ArchiveGameRow]) -> dict[int, list[str]]:
    """Each game's live plies in the notation, replayed from its starting position"""
    events = (await session.execute(
        select(
            col(GamePlyEvent.game_id),
            col(GamePlyEvent.from_i),
            col(GamePlyEvent.from_j),
            col(GamePlyEvent.to_i),
            col(GamePlyEvent.to_j),
            col(GamePlyEvent.morph_into)
        ).where(
            GamePlyEvent.game_id.in_([game.id for game in games]),  # type: ignore[attr-defined]
            GamePlyEvent.__table__.c.live_ply_index != None  # type: ignore[attr-defined]  # noqa: E711
        ).order_by(
            col(GamePlyEvent.game_id),
            col(GamePlyEvent.ply_index)
        )
    )).all()

    positions: dict[int, Position] = {
        game.id: position_from_sip(game.custom_starting_sip) if game.custom_starting_sip else Position.default_starting()
        for game in games
    }
    notations: dict[int, list[str]] = {game.id: [] for game in games}
    for event in events:
        ply = Ply(HexCoordinates(event.from_i, event.from_j), HexCoordinates(event.to_i, event.to_j), event.morph_into)
        position = positions[event.game_id]
        output = position.perform_ply(ply)
        notations[event.game_id].append(write_ply(ply, position, output.properties))
        positions[event.game_id] = output.new_position
    return notations


async def export_archive(
    session: AsyncSession,
    openings: OpeningMapping,
    root: AndNode,
    levels: list[SortLevel],
    columns: list[ArchiveColumn],
    include_moves: bool,
    game_url_template: str,
    locale: str,
    timezone: str,
    timeout_ms: int
) -> str:
    """Writes the whole result set to a temporary file and returns its path; the caller deletes it"""
    move_columns = await _max_move_count(session, openings, root, timeout_ms) if include_moves else 0

    descriptor, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(descriptor)
    workbook = xlsxwriter.Workbook(path, {"constant_memory": True, "remove_timezone": True})
    try:
        writer = _RowWriter(workbook, openings, game_url_template, locale, timezone)
        sheet = _MeasuredSheet(workbook.add_worksheet(), writer.formats)

        for column_index, column in enumerate(columns):
            sheet.write_string(0, column_index, writer.texts.columns[column], writer.formats.header)
        for move_index in range(move_columns):
            sheet.write_string(0, len(columns) + move_index, writer.texts.move.replace("[0]", str(move_index + 1)), writer.formats.header)

        row_index = 1
        batches: AsyncIterator[list[ArchiveGameRow]] = stream_archive_rows(session, openings, root, levels, timeout_ms)
        async for games in batches:
            notations = await _notations(session, games) if move_columns else {}
            for game in games:
                for column_index, column in enumerate(columns):
                    writer.write(sheet, row_index, column_index, column, game)
                for move_index, notation in enumerate(notations.get(game.id, [])[:move_columns]):
                    sheet.write_string(row_index, len(columns) + move_index, notation)
                row_index += 1
        sheet.fit_columns()
    finally:
        workbook.close()
    return path
