from fastapi import APIRouter, HTTPException, Query
from sqlmodel import col, desc, distinct, select

from net.base_router import LoggingRoute
from player.methods import resolve_player_refs
from study.models import ListStudiesPayload, Study, StudyCreate, StudyPublic, StudyTag, StudyUpdate, StudySummaryPublic
from study.datatypes import StudyPublicity
from common.dependencies import OptionalPlayerLoginDependency, SessionDependency, MandatoryPlayerLoginDependency


router = APIRouter(prefix="/study", route_class=LoggingRoute)


@router.post("/create", response_model=StudySummaryPublic, status_code=201)
async def create_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study: StudyCreate) -> StudySummaryPublic:
    db_study = study.build_table_model(client_login)

    session.add(db_study)
    await session.commit()

    await session.refresh(db_study)

    collected_refs = db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return db_study.to_summary(resolved_refs)


@router.post("/list", response_model=list[StudySummaryPublic])
async def list_studies(
    *,
    session: SessionDependency,
    payload: ListStudiesPayload,
    offset: int = 0,
    limit: int = Query(default=10, le=50)
) -> list[StudySummaryPublic]:
    query = select(Study).order_by(desc(Study.created_at), desc(Study.id)).offset(offset).limit(limit)

    if payload.author_login is not None:
        query = query.where(Study.author_login == payload.author_login)
        query = query.where(col(Study.publicity).in_([StudyPublicity.PUBLIC, StudyPublicity.PROFILE_AND_LINK_ONLY]))
    else:
        query = query.where(Study.publicity == StudyPublicity.PUBLIC)

    if payload.tags:
        fitting_ids = select(distinct(StudyTag.study_id)).where(col(StudyTag.tag).in_(payload.tags))
        query = query.where(col(Study.id).in_(fitting_ids))

    result = list(await session.exec(query))

    collected_refs = set()
    for db_study in result:
        collected_refs |= db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return [db_study.to_summary(resolved_refs) for db_study in result]


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
async def update_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study_id: int, study: StudyUpdate) -> StudyPublic:
    db_study = await session.get(Study, study_id)
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study deleted")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    db_study.sqlmodel_update(study.dump_for_table_model())  # noqa

    session.add(db_study)
    await session.commit()

    await session.refresh(db_study, attribute_names=["tags", "nodes"])

    collected_refs = db_study.collect_refs()
    resolved_refs = await resolve_player_refs(collected_refs, session)
    return db_study.to_public(resolved_refs)


@router.delete("/{study_id}")
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
