from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import col, desc, func, select

from net.base_router import LoggingRoute, rate_limited
from net.rate_limit import RateLimitGroup
from player.methods import resolve_player_refs
from study.models import ListStudiesPayload, ListStudiesResult, Study, StudyCreate, StudyPublic, StudyTag, StudyUpdate, StudySummaryPublic
from study.datatypes import StudyPublicity
from study.validation import validate_sip, validate_ply_tree
from common.dependencies import OptionalPlayerLoginDependency, SessionDependency, MandatoryPlayerLoginDependency
from utils.async_orm_session import AsyncSession


router = APIRouter(prefix="/study", route_class=LoggingRoute)


async def _commit_study(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:  # tags that differ for Python but not for the DB's collation, such as "e" and "\u00e9"
        await session.rollback()
        raise HTTPException(status_code=422, detail="Duplicate tags")


@router.post("/create", response_model=StudySummaryPublic, status_code=201)
@rate_limited(RateLimitGroup.WRITE)
async def create_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study: StudyCreate) -> StudySummaryPublic:
    db_study = study.build_table_model(client_login)
    validate_sip(study.key_sip)
    await validate_ply_tree(study.starting_sip, db_study.nodes)

    session.add(db_study)
    await _commit_study(session)

    await session.refresh(db_study)
    await session.refresh(db_study, attribute_names=["tags"])

    collected_refs = db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return db_study.to_summary(resolved_refs)


@router.post("/list", response_model=ListStudiesResult)
@rate_limited(RateLimitGroup.SEARCH)
async def list_studies(
    *,
    session: SessionDependency,
    client_login: OptionalPlayerLoginDependency,
    payload: ListStudiesPayload,
    offset: int = 0,
    limit: int = Query(default=10, le=50)
) -> ListStudiesResult:
    conditions: list[Any] = [Study.deleted == False]  # noqa: E712

    if payload.author_login is not None:
        conditions.append(Study.author_login == payload.author_login)
        if client_login != payload.author_login:
            conditions.append(col(Study.publicity).in_([StudyPublicity.PUBLIC, StudyPublicity.PROFILE_AND_LINK_ONLY]))
    else:
        conditions.append(Study.publicity == StudyPublicity.PUBLIC)

    for tag in payload.tags or []:
        conditions.append(col(Study.id).in_(select(StudyTag.study_id).where(StudyTag.tag == tag)))

    db_studies = list(await session.exec(select(
        Study
    ).where(
        *conditions
    ).order_by(
        desc(Study.created_at),
        desc(Study.id)
    ).offset(
        offset
    ).limit(
        limit
    ).options(
        selectinload(Study.tags)  # type: ignore[arg-type]
    )))
    total = (await session.exec(select(func.count(col(Study.id))).where(*conditions))).one()

    collected_refs = set()
    for db_study in db_studies:
        collected_refs |= db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return ListStudiesResult(
        studies=[db_study.to_summary(resolved_refs) for db_study in db_studies],
        total=total
    )


@router.get("/{study_id}", response_model=StudyPublic)
async def get_study(*, session: SessionDependency, study_id: int, client_login: OptionalPlayerLoginDependency) -> StudyPublic:
    db_study = await session.get(Study, study_id, options=Study.load_options())

    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.publicity == StudyPublicity.PRIVATE and client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Access restricted")

    collected_refs = db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return db_study.to_public(resolved_refs)


@router.patch("/{study_id}", response_model=StudyPublic)
@rate_limited(RateLimitGroup.WRITE)
async def update_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study_id: int, study: StudyUpdate) -> StudyPublic:
    db_study = await session.get(Study, study_id, options=Study.load_options())
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study deleted")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    updated_nodes = study.to_db_nodes()
    if study.key_sip:
        validate_sip(study.key_sip)
    if study.starting_sip or updated_nodes is not None:
        await validate_ply_tree(study.starting_sip or db_study.starting_sip, db_study.nodes if updated_nodes is None else updated_nodes)

    db_study.sqlmodel_update(study.dump_plain_fields())
    db_study.modified_at = datetime.now(UTC)

    updated_tags = study.to_db_tags()
    if updated_tags is not None:
        db_study.tags = updated_tags

    if updated_nodes is not None:
        db_study.nodes = updated_nodes
        db_study.key_path = study.key_path

    session.add(db_study)
    await _commit_study(session)

    await session.refresh(db_study)
    await session.refresh(db_study, attribute_names=["tags", "nodes"])

    collected_refs = db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return db_study.to_public(resolved_refs)


@router.delete("/{study_id}")
@rate_limited(RateLimitGroup.WRITE)
async def delete_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study_id: int) -> None:
    db_study = await session.get(Study, study_id)
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study has already been deleted before")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    db_study.deleted = True
    session.add(db_study)
    await session.commit()
