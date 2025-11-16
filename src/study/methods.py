from sqlmodel import Session, col, select, func

from src.study.models import Study
from src.study.datatypes import StudyPublicity


def get_player_studies_cnt(session: Session, author_login: str, include_private: bool) -> int:
    studies_selection_query = select(
        func.count(col(Study.id))
    ).where(
        Study.author_login == author_login
    )
    if not include_private:
        studies_selection_query = studies_selection_query.where(
            col(Study.publicity).in_([StudyPublicity.PROFILE_AND_LINK_ONLY, StudyPublicity.PUBLIC])
        )
    return session.exec(studies_selection_query).one()
