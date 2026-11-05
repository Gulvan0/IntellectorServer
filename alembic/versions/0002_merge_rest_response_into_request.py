"""Merge the REST response log into the request row

The response table had no timestamp of its own, so it could not be archived by day. The columns stay empty for a
request that was logged but never answered.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("restrequestlog", sa.Column("response_code", sa.Integer(), nullable=True))
    op.add_column("restrequestlog", sa.Column("response", mysql.TEXT(), nullable=True))
    op.execute(
        "UPDATE restrequestlog AS req JOIN restresponselog AS resp ON resp.request_id = req.id "
        "SET req.response_code = resp.response_code, req.response = resp.response"
    )
    op.drop_table("restresponselog")


def downgrade() -> None:
    op.create_table(
        "restresponselog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response", mysql.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["restrequestlog.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO restresponselog (request_id, response_code, response) "
        "SELECT id, response_code, response FROM restrequestlog WHERE response_code IS NOT NULL"
    )
    op.drop_column("restrequestlog", "response")
    op.drop_column("restrequestlog", "response_code")
