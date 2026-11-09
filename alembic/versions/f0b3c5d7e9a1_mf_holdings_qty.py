"""mf_holdings.qty: shares held, from the monthly portfolio disclosure, so buying and selling can be told apart from
price moves (a % of NAV changes with the price too)

Revision ID: f0b3c5d7e9a1
Revises: e9a2b4c6d8f0
Create Date: 2026-11-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0b3c5d7e9a1'
down_revision: Union[str, Sequence[str], None] = 'e9a2b4c6d8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_qty():
    return "qty" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("mf_holdings")}


def upgrade() -> None:
    if not _has_qty():
        with op.batch_alter_table("mf_holdings") as b:
            b.add_column(sa.Column("qty", sa.Float(), nullable=True))


def downgrade() -> None:
    if _has_qty():
        with op.batch_alter_table("mf_holdings") as b:
            b.drop_column("qty")
