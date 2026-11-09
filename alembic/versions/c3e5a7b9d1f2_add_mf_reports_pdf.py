"""add mf_reports.pdf: keep the Morningstar report PDF itself so MF Analysis can show it after the file is deleted

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-11-08 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("mf_reports")}


def upgrade() -> None:
    if "pdf" in _columns(op.get_bind()):
        return
    with op.batch_alter_table("mf_reports") as batch:
        batch.add_column(sa.Column("pdf", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    if "pdf" not in _columns(op.get_bind()):
        return
    with op.batch_alter_table("mf_reports") as batch:
        batch.drop_column("pdf")
