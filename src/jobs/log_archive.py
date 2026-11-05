"""Archives the log tables' whole days older than the retention: each day goes to `<destination>/<table>/<YYYY-MM-DD>.csv.zst`,
and once the upload is verified, is deleted from the table. Run from the repository root: `PYTHONPATH=src python -m jobs.log_archive`.

The destination is whatever rclone understands (`B2:intellector-backup/logs`, or a plain folder); rclone's own settings come
from its usual environment (RCLONE_CONFIG, RCLONE_CONFIG_<REMOTE>_*). Nothing at the destination is ever overwritten or deleted"""

import argparse
import csv
import json
import shutil
import subprocess
import tempfile
from compression import zstd
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Table, create_engine, delete, func, select
from sqlalchemy.engine import Connection

import net.core  # noqa: F401  # imports every model module
from config.loader import load
from config.models import MainConfig, SecretConfig
from config.stage import is_test_stage
from log.models import (
    ClientErrorLog,
    RESTRequestLog,
    TaskFailureLog,
    TimeoutCheckExecutedLog,
    TimeoutCheckPlannedLog,
    WSLog,
)


# the column holding the row's moment, per table
LOG_TABLES: dict[type[Any], str] = {
    RESTRequestLog: "ts",
    WSLog: "ts",
    ClientErrorLog: "ts",
    TaskFailureLog: "ts",
    TimeoutCheckExecutedLog: "event_time",
    TimeoutCheckPlannedLog: "event_time",
}
DEFAULT_RETENTION_DAYS = 7
DELETE_BATCH_SIZE = 5000
FETCH_BATCH_SIZE = 5000
LOCAL_TEST_DESTINATION = "log_archive_out"


def rclone(*args: str) -> str:
    result = subprocess.run([shutil.which("rclone") or "rclone", *args], capture_output=True, text=True)  # which(): finds .cmd wrappers on Windows
    if result.returncode != 0:
        raise RuntimeError(f"rclone {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def remote_size(path: str) -> int | None:
    """None if there is no such file"""
    listing = json.loads(rclone("lsjson", path))
    return listing[0]["Size"] if listing else None


def eligible_days(connection: Connection, table: Table, column_name: str, first_kept_day: date) -> list[date]:
    column = table.c[column_name]
    cutoff = datetime.combine(first_kept_day, time.min, tzinfo=UTC)
    rows = connection.execute(select(func.date(column)).where(column < cutoff).distinct().order_by(func.date(column)))
    return [row[0] for row in rows]


def export_day(connection: Connection, table: Table, column_name: str, day: date, target: Path) -> int:
    """Returns the number of rows written"""
    column = table.c[column_name]
    start = datetime.combine(day, time.min, tzinfo=UTC)
    query = select(table).where(column >= start, column < start + timedelta(days=1)).order_by(table.c.id)
    count = 0
    with zstd.open(target, "wt", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(table.c.keys())
        result = connection.execution_options(stream_results=True).execute(query)
        for batch in result.partitions(FETCH_BATCH_SIZE):
            for row in batch:
                writer.writerow([value.isoformat() if isinstance(value, datetime) else value for value in row])
            count += len(batch)
    return count


def delete_day(connection: Connection, table: Table, column_name: str, day: date) -> None:
    column = table.c[column_name]
    start = datetime.combine(day, time.min, tzinfo=UTC)
    statement = delete(table).where(column >= start, column < start + timedelta(days=1)).with_dialect_options(mysql_limit=DELETE_BATCH_SIZE)
    while connection.execute(statement).rowcount > 0:
        connection.commit()
    connection.commit()


def archive_day(connection: Connection, table: Table, column_name: str, day: date, destination: str) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        local_file = Path(temp_dir) / f"{day.isoformat()}.csv.zst"
        row_count = export_day(connection, table, column_name, day, local_file)
        if row_count == 0:
            return

        remote_path = f"{destination}/{table.name}/{day.isoformat()}.csv.zst"
        if remote_size(remote_path) is not None:
            # rows of an already archived day that arrived late: never overwrite
            remote_path = f"{destination}/{table.name}/{day.isoformat()}.{datetime.now(UTC):%H%M%S}.csv.zst"

        rclone("copyto", str(local_file), remote_path)
        if remote_size(remote_path) != local_file.stat().st_size:
            raise RuntimeError(f"Uploaded {remote_path} does not match the exported file; nothing was deleted")

    delete_day(connection, table, column_name, day)
    print(f"{table.name} {day}: {row_count} rows archived and purged")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", help="rclone path the archive goes under (required outside of the test stage)")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--optimize", action="store_true", help="OPTIMIZE every log table afterwards, to return the freed space")
    args = parser.parse_args()

    destination = args.destination
    if destination is None:
        if not is_test_stage():
            parser.error("--destination is required outside of the test stage")
        destination = LOCAL_TEST_DESTINATION

    load("main", MainConfig)  # fails early on a broken config, same as the server
    secret_config = load("secret", SecretConfig)
    engine = create_engine(secret_config.db.sync_url())
    first_kept_day = datetime.now(UTC).date() - timedelta(days=args.retention_days)

    failures = 0
    with engine.connect() as connection:
        for model, column_name in LOG_TABLES.items():
            table: Table = model.__table__  # type: ignore[attr-defined]
            for day in eligible_days(connection, table, column_name, first_kept_day):
                try:
                    archive_day(connection, table, column_name, day, destination)
                except Exception as error:
                    failures += 1
                    print(f"{table.name} {day}: FAILED: {error}")
                    connection.rollback()

        if args.optimize:
            for model in LOG_TABLES:
                table = model.__table__  # type: ignore[attr-defined]
                connection.exec_driver_sql(f"OPTIMIZE TABLE `{table.schema}`.`{table.name}`").fetchall()

    if failures:
        raise SystemExit(f"{failures} day(s) failed to archive")


if __name__ == "__main__":
    main()
