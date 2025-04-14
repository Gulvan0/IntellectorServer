from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlmodel import Session

from models import Study, StudyPublic
from .utils import get_session

router = APIRouter(prefix="/study")


@router.get("/{study_id}", response_model=StudyPublic)
async def get_study(*, session: Session = Depends(get_session), study_id: int):
    study = session.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study