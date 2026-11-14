from collections.abc import AsyncIterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.expression import Select
from sqlmodel import col

from board.opening import OpeningMapping
from game.archive.formula import AndNode, FormulaError, parse_formula
from game.archive.models import ArchiveGameRow, ArchiveSearchPayload, ArchiveSearchResult, SortLevelPayload
from game.archive.query import ArchiveExpressions, SortColumn, SortLevel
from game.models.main import Game, PlayerRatingPublic
from net.utils.rest_error import RestErrorCode, RestException
from player.methods import resolve_player_refs
from utils.async_orm_session import AsyncSession


MAX_EXECUTION_TIME_ERROR = 3024  # MySQL: the statement ran over its MAX_EXECUTION_TIME

DEFAULT_SORT = [SortLevel(SortColumn.ID, descending=True)]


def parse_request_formula(document: dict[str, Any]) -> AndNode:
    try:
        return parse_formula(document, resolved=True)
    except FormulaError as error:
        raise RestException(RestErrorCode.INVALID_FORMULA, str(error))


def sort_levels(payload_sort: list[SortLevelPayload]) -> list[SortLevel]:
    levels = [SortLevel(level.column, level.descending) for level in payload_sort]
    if len({level.column for level in levels}) != len(levels):
        raise RestException(RestErrorCode.INVALID_FORMULA, "A column can be sorted by only once")
    return levels or DEFAULT_SORT


def with_time_limit(query: Select[Any], timeout_ms: int) -> Select[Any]:
    return query.prefix_with(f"/*+ MAX_EXECUTION_TIME({int(timeout_ms)}) */")


@contextmanager
def translated_timeouts() -> Iterator[None]:
    try:
        yield
    except OperationalError as error:
        if error.orig is not None and getattr(error.orig, "args", [None])[0] == MAX_EXECUTION_TIME_ERROR:
            raise RestException(RestErrorCode.SEARCH_TIMEOUT, "The search took too long")
        raise


def filtered_query(expressions: ArchiveExpressions, root: AndNode, columns: list[Any], levels: list[SortLevel] | None = None) -> Select[Any]:
    try:
        condition = expressions.condition(root)
    except FormulaError as error:
        raise RestException(RestErrorCode.INVALID_FORMULA, str(error))
    order = expressions.order_by(levels) if levels is not None else []
    return expressions.joined_from(select(*columns)).where(condition).order_by(*order)


async def row_to_public(rows: list[Row[Any]], session: AsyncSession, openings: OpeningMapping) -> list[ArchiveGameRow]:
    refs: set[str] = set()
    for row in rows:
        refs.add(row.white_ref)
        refs.add(row.black_ref)
    resolved_refs = await resolve_player_refs(refs, session)

    result = []
    for row in rows:
        opening = openings.mapping.get(row.opening_sip)
        result.append(ArchiveGameRow(
            id=row.id,
            white_player=resolved_refs.get(row.white_ref),
            black_player=resolved_refs.get(row.black_ref),
            white_rating=PlayerRatingPublic.of(row.white_elo, row.white_elo_provisional),
            black_rating=PlayerRatingPublic.of(row.black_elo, row.black_elo_provisional),
            started_at=row.started_at,
            ended_at=row.ended_at,
            duration_ms=int(row.duration_ms) if row.duration_ms is not None else None,
            time_control_kind=row.time_control_kind,
            start_seconds=row.start_seconds,
            increment_seconds=row.increment_seconds,
            rated=row.rated,
            custom_starting_sip=row.custom_starting_sip,
            opening_id=opening.id if opening else None,
            ended=bool(row.ended),
            outcome_kind=row.outcome_kind,
            winner=row.winner,
            move_count=int(row.move_count),
            white_time_left_ms=int(row.white_time_left_ms) if row.white_time_left_ms is not None else None,
            black_time_left_ms=int(row.black_time_left_ms) if row.black_time_left_ms is not None else None,
        ))
    return result


async def search_archive(
    session: AsyncSession,
    openings: OpeningMapping,
    payload: ArchiveSearchPayload,
    timeout_ms: int
) -> ArchiveSearchResult:
    root = parse_request_formula(payload.formula)
    levels = sort_levels(payload.sort)
    expressions = ArchiveExpressions(datetime.now(UTC), openings)

    count_query = with_time_limit(filtered_query(expressions, root, [func.count(col(Game.id))]), timeout_ms)
    page_query = with_time_limit(
        filtered_query(expressions, root, expressions.row_columns(), levels)
        .offset(payload.offset)
        .limit(payload.limit),
        timeout_ms
    )

    with translated_timeouts():
        total = (await session.execute(count_query)).scalar_one()
        rows = list((await session.execute(page_query)).all())

    return ArchiveSearchResult(games=await row_to_public(rows, session, openings), total=total)


async def stream_archive_rows(
    session: AsyncSession,
    openings: OpeningMapping,
    root: AndNode,
    levels: list[SortLevel],
    timeout_ms: int,
    batch_size: int = 500
) -> AsyncIterator[list[ArchiveGameRow]]:
    """The whole result set, in batches, for the export. `now` is read once, so that every batch agrees on it"""
    expressions = ArchiveExpressions(datetime.now(UTC), openings)
    query = filtered_query(expressions, root, expressions.row_columns(), levels)
    offset = 0
    while True:
        with translated_timeouts():
            rows = list((await session.execute(with_time_limit(query.offset(offset).limit(batch_size), timeout_ms))).all())
        if not rows:
            return
        yield await row_to_public(rows, session, openings)
        if len(rows) < batch_size:
            return
        offset += batch_size
