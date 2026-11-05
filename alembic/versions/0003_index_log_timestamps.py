"""Index the log tables' timestamps and authors, which the archive job and the last-seen lookup filter by

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 23:35:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Named as SQLModel names them for tables of the intellector_logs schema, which these become in the next revision
INDEXED_COLUMNS = {
    "restrequestlog": ["ts", "authorized_as"],
    "wslog": ["ts", "authorized_as"],
    "clienterrorlog": ["ts", "authorized_as"],
    "taskfailurelog": ["ts"],
    "timeoutcheckexecutedlog": ["event_time"],
    "timeoutcheckplannedlog": ["event_time"],
}


def index_name(table: str, column: str) -> str:
    return f"ix_intellector_logs_{table}_{column}"


def upgrade() -> None:
    for table, columns in INDEXED_COLUMNS.items():
        for column in columns:
            op.create_index(index_name(table, column), table, [column])


def downgrade() -> None:
    for table, columns in INDEXED_COLUMNS.items():
        for column in columns:
            op.drop_index(index_name(table, column), table)
