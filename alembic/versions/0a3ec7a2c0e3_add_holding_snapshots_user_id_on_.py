"""add holding_snapshots, user_id on portfolio_snapshots and portfolio_plan

Revision ID: 0a3ec7a2c0e3
Revises: 218d401380ff
Create Date: 2026-10-08 00:39:26.875723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a3ec7a2c0e3'
down_revision: Union[str, Sequence[str], None] = '218d401380ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "holding_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holding_id", sa.Integer(), sa.ForeignKey("holdings.id"), nullable=False),
        sa.Column("snap_date", sa.Text(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("cmp", sa.Float(), nullable=True),
        sa.Column("present", sa.Float(), nullable=True),
        sa.Column("invested", sa.Float(), nullable=True),
        sa.UniqueConstraint("holding_id", "snap_date"),
    )
    op.create_index(
        "idx_holding_snapshots_holding", "holding_snapshots", ["holding_id", "snap_date"]
    )

    # portfolio_snapshots and portfolio_plan are created lazily by portfolio.py's ensure(),
    # the first time a route touches them - not by database.py's migrations, which run
    # unconditionally at every startup. On a brand-new database, app.py's `alembic upgrade
    # head` runs before any request does, so neither table exists yet: ALTERing them would
    # fail outright. Create them directly in their final shape in that case; only ALTER the
    # old shape (and backfill existing rows to user_id=1) when there's data to preserve.
    existing = sa.inspect(op.get_bind()).get_table_names()

    if "portfolio_snapshots" not in existing:
        op.create_table(
            "portfolio_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("snap_date", sa.Text(), nullable=False),
            sa.Column("total", sa.Float(), nullable=True),
            sa.Column("invested", sa.Float(), nullable=True),
            sa.Column("groups", sa.Text(), nullable=True),
            sa.UniqueConstraint("user_id", "snap_date", name="uq_portfolio_snapshots_user_date"),
        )
    else:
        # portfolio_snapshots: was PRIMARY KEY(snap_date), single-user. Rebuild with a
        # surrogate id and (user_id, snap_date) unique so multiple users can each have
        # their own snapshot for the same date. Existing rows backfill user_id=1.
        with op.batch_alter_table("portfolio_snapshots", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"))
        op.execute("UPDATE portfolio_snapshots SET id = rowid WHERE id IS NULL")
        with op.batch_alter_table("portfolio_snapshots", recreate="always") as batch_op:
            batch_op.alter_column("id", nullable=False)
            batch_op.create_primary_key("pk_portfolio_snapshots", ["id"])
            batch_op.create_unique_constraint(
                "uq_portfolio_snapshots_user_date", ["user_id", "snap_date"]
            )

    if "portfolio_plan" not in existing:
        op.create_table(
            "portfolio_plan",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.UniqueConstraint("user_id", "key", name="uq_portfolio_plan_user_key"),
        )
    else:
        # portfolio_plan: was PRIMARY KEY(key), single-user. Same rebuild.
        with op.batch_alter_table("portfolio_plan", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"))
        op.execute("UPDATE portfolio_plan SET id = rowid WHERE id IS NULL")
        with op.batch_alter_table("portfolio_plan", recreate="always") as batch_op:
            batch_op.alter_column("id", nullable=False)
            batch_op.create_primary_key("pk_portfolio_plan", ["id"])
            batch_op.create_unique_constraint("uq_portfolio_plan_user_key", ["user_id", "key"])


def downgrade() -> None:
    with op.batch_alter_table("portfolio_plan", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_portfolio_plan_user_key", type_="unique")
        batch_op.drop_column("user_id")
        batch_op.drop_column("id")
        batch_op.create_primary_key("pk_portfolio_plan", ["key"])

    with op.batch_alter_table("portfolio_snapshots", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_portfolio_snapshots_user_date", type_="unique")
        batch_op.drop_column("user_id")
        batch_op.drop_column("id")
        batch_op.create_primary_key("pk_portfolio_snapshots", ["snap_date"])

    op.drop_index("idx_holding_snapshots_holding", table_name="holding_snapshots")
    op.drop_table("holding_snapshots")
