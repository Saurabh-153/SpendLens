"""add vacations: coloured date ranges on the reminder calendar

Revision ID: d5f7b0c3e8a2
Revises: c4e6a9b2d7f1
Create Date: 2026-10-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text


# revision identifiers, used by Alembic.
revision: str = 'd5f7b0c3e8a2'
down_revision: Union[str, Sequence[str], None] = 'c4e6a9b2d7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vacations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("end_date", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False, server_default="#0f8a8a"),
        sa.Column("created_at", sa.String(), nullable=False, server_default=now_text(op.get_bind())),
    )


def downgrade() -> None:
    op.drop_table("vacations")
