"""Saved game archive filters, with the two authorless ones the server manages

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 12:00:00

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

import common.field_types


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ONGOING_CONDITION = {"property": "result", "values": ["ongoing"]}
AUTHORLESS_FILTERS = [
    ("ongoing", "Ongoing games", {"version": 1, "root": {"and": [ONGOING_CONDITION]}}),
    ("archive", "Game archive", {"version": 1, "root": {"and": [{"not": ONGOING_CONDITION}]}}),
]


def upgrade() -> None:
    table = op.create_table(
        'savedgamefilter',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('author_login', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('key', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column('formula', sa.JSON(), nullable=False),
        sa.Column('created_at', common.field_types.UtcDateTime(None), nullable=False),
        sa.Column('updated_at', common.field_types.UtcDateTime(None), nullable=False),
        sa.ForeignKeyConstraint(['author_login'], ['player.login'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('author_login', 'name', name='uq_saved_filter_author_name'),
        sa.UniqueConstraint('key')
    )
    now = datetime.now(UTC)
    op.bulk_insert(table, [
        {"author_login": None, "key": key, "name": name, "formula": formula, "created_at": now, "updated_at": now}
        for key, name, formula in AUTHORLESS_FILTERS
    ])


def downgrade() -> None:
    op.drop_table('savedgamefilter')
