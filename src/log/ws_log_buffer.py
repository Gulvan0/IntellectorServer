import asyncio

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from log.models import WSLog


FLUSH_INTERVAL_SECS = 1.0
FLUSH_THRESHOLD = 500


class WSLogBuffer:
    """Collects outgoing WS log rows and inserts them in batches, keeping the DB off the send path.
    A broadcast to N subscribers thus costs one multi-row insert instead of N commits"""

    def __init__(self, db_engine: AsyncEngine) -> None:
        self.__db_engine = db_engine
        self.__rows: list[WSLog] = []
        self.__threshold_reached = asyncio.Event()

    def add(self, row: WSLog) -> None:
        # row.ts is stamped on construction, so it records the send time, not the flush time
        self.__rows.append(row)
        if len(self.__rows) >= FLUSH_THRESHOLD:
            self.__threshold_reached.set()

    async def wait_until_flush_due(self) -> None:
        try:
            await asyncio.wait_for(self.__threshold_reached.wait(), timeout=FLUSH_INTERVAL_SECS)
        except TimeoutError:
            pass

    async def flush(self) -> None:
        self.__threshold_reached.clear()
        if not self.__rows:
            return

        batch, self.__rows = self.__rows, []
        try:
            async with self.__db_engine.begin() as connection:
                # a single writer inserting in add() order keeps the autoincrement ids in send order
                await connection.execute(insert(WSLog), [row.model_dump(exclude={"id"}) for row in batch])
        except Exception:
            self.__rows = batch + self.__rows  # retried on the next flush
            raise
