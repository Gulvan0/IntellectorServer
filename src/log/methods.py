import asyncio
from datetime import datetime

from sqlmodel import select, func

from log.models import RESTRequestLog, WSLog
from utils.async_orm_session import AsyncSession


async def last_seen_in_logs(session: AsyncSession, login: str) -> datetime | None:
    rest_result, ws_result = await asyncio.gather(
        session.exec(select(func.max(RESTRequestLog.ts)).where(RESTRequestLog.authorized_as == login)),
        session.exec(select(func.max(WSLog.ts)).where(WSLog.authorized_as == login)),
    )
    rest_ts = rest_result.first()
    ws_ts = ws_result.first()
    if rest_ts and ws_ts:
        return max(rest_ts, ws_ts)
    else:
        return rest_ts or ws_ts
