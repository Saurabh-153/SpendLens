"""mf_fund_months.fund_manager (the manager names as plain text) and the exact as-on date on mf_fund_months and
mf_sources, next to the month

Revision ID: a1c3e5f7b9d2
Revises: f0b3c5d7e9a1
Create Date: 2026-11-08 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'f0b3c5d7e9a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADD = (("mf_fund_months", "fund_manager"), ("mf_fund_months", "as_on"), ("mf_sources", "as_on"))


def _cols(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table in ("mf_fund_months", "mf_sources"):
        missing = [c for t, c in ADD if t == table and c not in _cols(table)]
        if missing:
            with op.batch_alter_table(table) as b:
                for c in missing:
                    b.add_column(sa.Column(c, sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    for table in ("mf_fund_months", "mf_sources"):
        present = [c for t, c in ADD if t == table and c in _cols(table)]
        if present:
            with op.batch_alter_table(table) as b:
                for c in present:
                    b.drop_column(c)
