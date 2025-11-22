from sqlmodel import col, select, func

from src.study.models import Study
from src.study.datatypes import StudyPublicity
from src.utils.async_orm_session import AsyncSession


async def get_player_studies_cnt(session: AsyncSession, author_login: str, include_private: bool) -> int:
    studies_selection_query = select(
        func.count(col(Study.id))
    ).where(
        Study.author_login == author_login
    )
    if not include_private:
        studies_selection_query = studies_selection_query.where(
            col(Study.publicity).in_([StudyPublicity.PROFILE_AND_LINK_ONLY, StudyPublicity.PUBLIC])
        )
    result = await session.exec(studies_selection_query)
    return result.one()
