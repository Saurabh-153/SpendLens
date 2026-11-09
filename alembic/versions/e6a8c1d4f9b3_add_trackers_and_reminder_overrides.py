"""add day trackers (trackers, tracker_days, tracker_cost_links) and reminder_overrides for drag-to-move

Revision ID: e6a8c1d4f9b3
Revises: d5f7b0c3e8a2
Create Date: 2026-10-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text


# revision identifiers, used by Alembic.
revision: str = 'e6a8c1d4f9b3'
down_revision: Union[str, Sequence[str], None] = 'd5f7b0c3e8a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trackers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False, server_default="#7a52d6"),
        sa.Column("target_per_week", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("weekdays", sa.String(), nullable=False, server_default="0,1,2,3,4,5,6"),
        sa.Column("pause_on", sa.String(), nullable=False, server_default="vacation"),
        sa.Column("bill_reminder_id", sa.Integer(), sa.ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False, server_default=now_text(op.get_bind())),
    )
    op.create_table(
        "tracker_cost_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tracker_id", sa.Integer(), sa.ForeignKey("trackers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_subcategory_id", sa.Integer(), sa.ForeignKey("subcategories.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_table(
        "tracker_days",
        sa.Column("tracker_id", sa.Integer(), sa.ForeignKey("trackers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date", sa.String(), primary_key=True),
    )
    op.create_table(
        "reminder_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reminder_id", sa.Integer(), sa.ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.UniqueConstraint("reminder_id", "month"),
    )


def downgrade() -> None:
    op.drop_table("reminder_overrides")
    op.drop_table("tracker_days")
    op.drop_table("tracker_cost_links")
    op.drop_table("trackers")
