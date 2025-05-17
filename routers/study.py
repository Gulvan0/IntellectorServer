from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import StringConstraints
from sqlmodel import col, distinct, select, Session

from globalstate import GlobalState
from models import Study, StudyCreate, StudyPublic, StudyTag, StudyUpdate
from utils.datatypes import StudyPublicity
from .utils import get_session, OPTIONAL_USER_TOKEN_HEADER_SCHEME, USER_TOKEN_HEADER_SCHEME

router = APIRouter(prefix="/study")


@router.get("/{study_id}", response_model=StudyPublic)
async def get_study(*, session: Session = Depends(get_session), study_id: int, token: str | None = Depends(OPTIONAL_USER_TOKEN_HEADER_SCHEME)):
    client_login = None
    if token is not None:
        client = GlobalState.token_to_user.get(token)
        if not client:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not client.is_guest():
            client_login = client.login

    db_study = session.get(Study, study_id)

    if not db_study:
        raise HTTPException(status_code=404, detail="Study not found")

    if db_study.publicity == StudyPublicity.PRIVATE and client_login != db_study.author_login:
        raise HTTPException(status_code=403, detail="Access restricted")

    return db_study


@router.post("/create", response_model=StudyPublic, status_code=201)
async def create_study(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), study: StudyCreate):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    client_login = client.login

    db_study = study.build_table_model(client_login)

    session.add(db_study)
    session.commit()

    session.refresh(db_study)
    return db_study


@router.patch("/{study_id}", response_model=StudyPublic)
async def update_study(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), study_id: int, study: StudyUpdate):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    client_login = client.login

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
async def delete_study(*, session: Session = Depends(get_session), token: str = Depends(USER_TOKEN_HEADER_SCHEME), study_id: int):
    client = GlobalState.token_to_user.get(token)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid token")
    if client.is_guest():
        raise HTTPException(status_code=403, detail="Login required")
    client_login = client.login

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
