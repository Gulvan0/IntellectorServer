from fastapi import APIRouter, HTTPException, Query
from sqlmodel import col, distinct, select

from src.common.field_types import PlayerLogin
from src.net.base_router import LoggingRoute
from src.study.models import Study, StudyCreate, StudyPublic, StudyTag, StudyUpdate
from src.study.datatypes import StudyPublicity
from src.common.dependencies import OptionalPlayerLoginDependency, SessionDependency, MandatoryPlayerLoginDependency


router = APIRouter(prefix="/study", route_class=LoggingRoute)


@router.post("/create", response_model=StudyPublic, status_code=201)
async def create_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study: StudyCreate):
    db_study = study.build_table_model(client_login)

    session.add(db_study)
    await session.commit()

    await session.refresh(db_study)
    return await db_study.to_public(session)


@router.get("/list", response_model=list[StudyPublic])
async def list_studies(
    *,
    session: SessionDependency,
    author_login: PlayerLogin | None = None,
    tags: list[str] | None = None,
    offset: int = 0,
    limit: int = Query(default=10, le=50)
):
    query = select(Study)

    if author_login is not None:
        query = query.where(Study.author_login == author_login)
        query = query.where(col(Study.publicity).in_([StudyPublicity.PUBLIC, StudyPublicity.PROFILE_AND_LINK_ONLY]))
    else:
        query = query.where(Study.publicity == StudyPublicity.PUBLIC)

    if tags:
        fitting_ids = select(distinct(StudyTag.study_id)).where(col(StudyTag.tag).in_(tags))
        query = query.where(col(Study.id).in_(fitting_ids))

    query = query.offset(offset).limit(limit)
    result = await session.exec(query)
    return [await db_study.to_public(session) for db_study in result]


@router.get("/{study_id}", response_model=StudyPublic)
async def get_study(*, session: SessionDependency, study_id: int, client_login: OptionalPlayerLoginDependency):
    db_study = await session.get(Study, study_id)

    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.publicity == StudyPublicity.PRIVATE and client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Access restricted")

    return await db_study.to_public(session)


@router.patch("/{study_id}", response_model=StudyPublic)
async def update_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study_id: int, study: StudyUpdate):
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

    await session.refresh(db_study)
    return await db_study.to_public(session)


@router.delete("/{study_id}")
async def delete_study(*, session: SessionDependency, client_login: MandatoryPlayerLoginDependency, study_id: int):
    db_study = await session.get(Study, study_id)
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study has already been deleted before")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    db_study.sqlmodel_update(dict(deleted=True))  # noqa
    await session.commit()

    return dict(ok=True)
