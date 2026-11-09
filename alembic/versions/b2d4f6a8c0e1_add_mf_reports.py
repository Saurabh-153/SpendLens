"""add mf_reports: third-party fund reports (Morningstar) kept to cross-check the AMC factsheets

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-11-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text, table_names


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _text(name):
    return sa.Column(name, sa.String(), nullable=False, server_default="")


def upgrade() -> None:
    bind = op.get_bind()
    if "mf_reports" in table_names(bind):
        return
    op.create_table(
        "mf_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(), nullable=False, server_default="morningstar"),
        sa.Column("scheme_key", sa.String(), nullable=False),
        sa.Column("scheme", sa.String(), nullable=False),
        _text("isin"),
        sa.Column("report_date", sa.String(), nullable=False),
        _text("month"),
        sa.Column("data", sa.Text(), nullable=False, server_default=""),
        _text("file_name"), _text("sha256"),
        sa.Column("imported_at", sa.String(), nullable=False, server_default=now_text(bind)),
        sa.UniqueConstraint("user_id", "source", "scheme_key", "report_date"),
    )


def downgrade() -> None:
    if "mf_reports" in table_names(op.get_bind()):
        op.drop_table("mf_reports")
