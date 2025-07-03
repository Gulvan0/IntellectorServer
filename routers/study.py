from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import StringConstraints
from sqlmodel import col, distinct, select, Session

from models import Study, StudyCreate, StudyPublic, StudyTag, StudyUpdate
from utils.datatypes import StudyPublicity
from .utils import get_mandatory_player_login, get_optional_player_login, get_session

router = APIRouter(prefix="/study")


@router.get("/{study_id}", response_model=StudyPublic)
async def get_study(*, session: Session = Depends(get_session), study_id: int, client_login: str | None = Depends(get_optional_player_login)):
    db_study = session.get(Study, study_id)

    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.publicity == StudyPublicity.PRIVATE and client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Access restricted")

    return db_study


@router.post("/create", response_model=StudyPublic, status_code=201)
async def create_study(*, session: Session = Depends(get_session), client_login: str = Depends(get_mandatory_player_login), study: StudyCreate):
    db_study = study.build_table_model(client_login)

    session.add(db_study)
    session.commit()

    session.refresh(db_study)
    return db_study


@router.patch("/{study_id}", response_model=StudyPublic)
async def update_study(*, session: Session = Depends(get_session), client_login: str = Depends(get_mandatory_player_login), study_id: int, study: StudyUpdate):
    db_study = session.get(Study, study_id)
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study deleted")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    db_study.sqlmodel_update(study.dump_for_table_model())  # noqa

    session.add(db_study)
    session.commit()

    session.refresh(db_study)
    return db_study


@router.delete("/{study_id}")
async def delete_study(*, session: Session = Depends(get_session), client_login: str = Depends(get_mandatory_player_login), study_id: int):
    db_study = session.get(Study, study_id)
    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.deleted:
        raise HTTPException(status_code=410, detail="Study has already been deleted before")

    if client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Not the study's author")

    db_study.sqlmodel_update(dict(deleted=True))  # noqa
    session.commit()

    return dict(ok=True)


@router.get("/list", response_model=list[StudyPublic])
async def list_studies(
    *,
    session: Session = Depends(get_session),
    author_login: Annotated[str, StringConstraints(to_lower=True)] | None = None,
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
    return session.exec(query).all()  # noqa
