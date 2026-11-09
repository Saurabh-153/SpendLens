"""goal kinds (large / small / recurring), target month and recurring-expense fields on portfolio_goals

Revision ID: c7e2f9a4b1d3
Revises: b1e3a6c8d0f2
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e2f9a4b1d3'
down_revision: Union[str, Sequence[str], None] = 'b1e3a6c8d0f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SMALL_BELOW = 500000  # one-time default: goals under ₹5L become small goals (editable per goal afterwards)


def columns():
    """Fresh Column objects each call (a Column can only be attached to one table)."""
    return [
        sa.Column("kind", sa.String(), nullable=False, server_default="large"),
        sa.Column("target_month", sa.Integer(), nullable=True),
        sa.Column("every_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("escalation_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("subcategory_id", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("portfolio_goals")}
    for col in columns():
        if col.name not in have:
            op.add_column("portfolio_goals", col)
    if "kind" not in have:
        op.execute(sa.text("UPDATE portfolio_goals SET kind = 'small' WHERE target_amount < :cut").bindparams(cut=SMALL_BELOW))


def downgrade() -> None:
    with op.batch_alter_table("portfolio_goals") as batch_op:
        for col in reversed(columns()):
            batch_op.drop_column(col.name)
