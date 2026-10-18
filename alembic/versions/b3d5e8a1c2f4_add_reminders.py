"""add reminder calendar tables

Revision ID: b3d5e8a1c2f4
Revises: 7fa60c624af4
Create Date: 2026-10-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text


# revision identifiers, used by Alembic.
revision: str = 'b3d5e8a1c2f4'
down_revision: Union[str, Sequence[str], None] = '7fa60c624af4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED = [
    ("Bills & EMI", "#f5b942", None, 1),
    ("Card dates", "#fb7185", "card", 2),
    ("SIPs", "#3ecf8e", "sip", 3),
]


def upgrade() -> None:
    op.create_table(
        "reminder_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False, server_default="#64748b"),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("reminder_categories.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("repeat", sa.String(), nullable=False, server_default="monthly"),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("expense_category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expense_subcategory_id", sa.Integer(), sa.ForeignKey("subcategories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False, server_default=now_text(op.get_bind())),
    )
    op.create_index("ix_reminders_category_id", "reminders", ["category_id"])
    op.create_table(
        "reminder_settings",
        sa.Column("user_id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("nudge_on", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nudge_time", sa.String(), nullable=False, server_default="21:00"),
    )
    cats = sa.table(
        "reminder_categories",
        sa.column("user_id", sa.Integer), sa.column("name", sa.String), sa.column("color", sa.String),
        sa.column("kind", sa.String), sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(cats, [{"user_id": 1, "name": n, "color": c, "kind": k, "sort_order": s} for n, c, k, s in SEED])


def downgrade() -> None:
    op.drop_table("reminder_settings")
    op.drop_index("ix_reminders_category_id", table_name="reminders")
    op.drop_table("reminders")
    op.drop_table("reminder_categories")
