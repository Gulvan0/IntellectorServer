"""Move the password table to the intellector_sensitive database

The read-only search user gets SELECT on the whole main database, so that every table added to it later is searchable;
secrets therefore live elsewhere. The foreign key to `player` is dropped, so that either database restores without the other.
The database itself is created by bootstrap (a migration user needs no CREATE DATABASE right).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SENSITIVE_DATABASE = "intellector_sensitive"
TABLE = "playerpassword"


def upgrade() -> None:
    foreign_keys = op.get_bind().execute(sa.text(
        "SELECT constraint_name FROM information_schema.referential_constraints "
        "WHERE constraint_schema = DATABASE() AND table_name = :table"
    ), {"table": TABLE}).scalars().all()
    for name in foreign_keys:
        op.drop_constraint(name, TABLE, type_="foreignkey")
    op.execute(f"RENAME TABLE `{TABLE}` TO `{SENSITIVE_DATABASE}`.`{TABLE}`")


def downgrade() -> None:
    op.execute(f"RENAME TABLE `{SENSITIVE_DATABASE}`.`{TABLE}` TO `{TABLE}`")
    op.create_foreign_key(None, TABLE, "player", ["login"], ["login"])
