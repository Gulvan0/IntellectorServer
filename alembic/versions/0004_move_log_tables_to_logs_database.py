"""Move the log tables to the intellector_logs database

A restore of the main database then never wipes the last week of logs, and the backups need no exclusion list.
The database itself is created by bootstrap (a migration user needs no CREATE DATABASE right).
RENAME TABLE moves the rows and indexes along with the table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04 23:40:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LOGS_DATABASE = "intellector_logs"
LOG_TABLES = [
    "restrequestlog",
    "wslog",
    "clienterrorlog",
    "taskfailurelog",
    "timeoutcheckexecutedlog",
    "timeoutcheckplannedlog",
]


def upgrade() -> None:
    for table in LOG_TABLES:
        op.execute(f"RENAME TABLE `{table}` TO `{LOGS_DATABASE}`.`{table}`")


def downgrade() -> None:
    for table in LOG_TABLES:
        op.execute(f"RENAME TABLE `{LOGS_DATABASE}`.`{table}` TO `{table}`")
