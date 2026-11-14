import os
from datetime import UTC, date, datetime

from fastapi import APIRouter
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from common.dependencies import (
    MainConfigDependency,
    MandatoryPlayerLoginDependency,
    OpeningMappingDepencency,
    SearchSessionDependency,
    SessionDependency,
)
from game.archive.export import export_archive
from game.archive.formula import FormulaError, parse_formula
from game.archive.methods import parse_request_formula, search_archive, sort_levels
from game.archive.models import (
    ArchiveExportPayload,
    ArchiveSearchPayload,
    ArchiveSearchResult,
    SavedFilterPublic,
    SavedFilterSummary,
    SavedGameFilter,
    SaveFilterPayload,
)
from net.base_router import LoggingRoute, rate_limited
from net.rate_limit import RateLimitGroup
from net.utils.rest_error import RestErrorCode, RestException
from player.methods import resolve_player_ref
from utils.async_orm_session import AsyncSession


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


router = APIRouter(prefix="/game/archive", route_class=LoggingRoute)


@router.post("/search", response_model=ArchiveSearchResult)
@rate_limited(RateLimitGroup.SEARCH)
async def search_route(
    *,
    session: SearchSessionDependency,
    openings: OpeningMappingDepencency,
    main_config: MainConfigDependency,
    payload: ArchiveSearchPayload
) -> ArchiveSearchResult:
    return await search_archive(session, openings, payload, main_config.limits.search_timeout_ms)


@router.post("/export", response_class=FileResponse)
@rate_limited(RateLimitGroup.EXPORT)
async def export_route(
    *,
    session: SearchSessionDependency,
    openings: OpeningMappingDepencency,
    main_config: MainConfigDependency,
    payload: ArchiveExportPayload
) -> FileResponse:
    if len(set(payload.columns)) != len(payload.columns):
        raise RestException(RestErrorCode.INVALID_FORMULA, "A column can be exported only once")

    path = await export_archive(
        session,
        openings,
        parse_request_formula(payload.formula),
        sort_levels(payload.sort),
        payload.columns,
        payload.include_moves,
        payload.locale,
        payload.timezone,
        main_config.limits.search_timeout_ms
    )
    return FileResponse(
        path,
        media_type=XLSX_MEDIA_TYPE,
        filename=f"intellector_games_{date.today().isoformat()}.xlsx",
        background=BackgroundTask(os.remove, path)
    )


async def _to_public(db_filter: SavedGameFilter, session: AsyncSession) -> SavedFilterPublic:
    assert db_filter.id is not None
    return SavedFilterPublic(
        id=db_filter.id,
        key=db_filter.key,
        name=db_filter.name,
        author=await resolve_player_ref(db_filter.author_login, session) if db_filter.author_login else None,
        formula=db_filter.formula
    )


@router.get("/filters", response_model=list[SavedFilterSummary])
async def list_filters(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency) -> list[SavedFilterSummary]:
    db_filters = await session.exec(
        select(SavedGameFilter).where(SavedGameFilter.author_login == client_login).order_by(col(SavedGameFilter.name))
    )
    return [SavedFilterSummary(id=db_filter.id, name=db_filter.name) for db_filter in db_filters if db_filter.id is not None]


@router.get("/filters/{id_or_key}", response_model=SavedFilterPublic)
async def get_filter(*, session: SessionDependency, id_or_key: str) -> SavedFilterPublic:
    """A user's filter by its id, an authorless one by its key: a key is never a number"""
    if id_or_key.isdigit():
        db_filter = await session.get(SavedGameFilter, int(id_or_key))
    else:
        db_filter = (await session.exec(select(SavedGameFilter).where(SavedGameFilter.key == id_or_key))).first()
    if not db_filter:
        raise RestException(RestErrorCode.FILTER_NOT_FOUND, "Filter not found")
    return await _to_public(db_filter, session)


@router.put("/filters", response_model=SavedFilterPublic)
@rate_limited(RateLimitGroup.WRITE)
async def save_filter(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, payload: SaveFilterPayload) -> SavedFilterPublic:
    """Overwrites the client's filter of the same name (compared as the DB's collation does) only if `overwrite` is set"""
    try:
        parse_formula(payload.formula, resolved=False)
    except FormulaError as error:
        raise RestException(RestErrorCode.INVALID_FORMULA, str(error))

    existing = (await session.exec(
        select(SavedGameFilter).where(SavedGameFilter.author_login == client_login, SavedGameFilter.name == payload.name)
    )).first()

    if existing:
        if not payload.overwrite:
            raise RestException(RestErrorCode.FILTER_NAME_TAKEN, "A filter with this name exists")
        existing.name = payload.name
        existing.formula = payload.formula
        existing.updated_at = datetime.now(UTC)
        db_filter = existing
    else:
        db_filter = SavedGameFilter(author_login=client_login, name=payload.name, formula=payload.formula)

    session.add(db_filter)
    try:
        await session.commit()
    except IntegrityError:  # a concurrent save of the same name
        await session.rollback()
        raise RestException(RestErrorCode.FILTER_NAME_TAKEN, "A filter with this name exists")
    await session.refresh(db_filter)
    return await _to_public(db_filter, session)


@router.delete("/filters/{filter_id}", status_code=204)
@rate_limited(RateLimitGroup.WRITE)
async def delete_filter(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, filter_id: int) -> None:
    db_filter = await session.get(SavedGameFilter, filter_id)
    if not db_filter or db_filter.author_login != client_login:
        raise RestException(RestErrorCode.FILTER_NOT_FOUND, "Filter not found")
    await session.delete(db_filter)
    await session.commit()
