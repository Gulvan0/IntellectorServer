from datetime import datetime

from sqlmodel import select, func

from log.models import RESTRequestLog, WSLog
from utils.async_orm_session import AsyncSession


async def last_seen_in_logs(session: AsyncSession, login: str) -> datetime | None:
    rest_ts = (await session.exec(select(func.max(RESTRequestLog.ts)).where(RESTRequestLog.authorized_as == login))).first()
    ws_ts = (await session.exec(select(func.max(WSLog.ts)).where(WSLog.authorized_as == login, WSLog.incoming == True))).first()  # noqa: E712
    if rest_ts and ws_ts:
        return max(rest_ts, ws_ts)
    else:
        return rest_ts or ws_ts
