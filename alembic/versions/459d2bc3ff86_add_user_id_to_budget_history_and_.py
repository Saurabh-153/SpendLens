"""add user_id to budget_history and settings

Revision ID: 459d2bc3ff86
Revises: 0a3ec7a2c0e3
Create Date: 2026-10-08 00:45:12.329908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '459d2bc3ff86'
down_revision: Union[str, Sequence[str], None] = '0a3ec7a2c0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # budget_history: was PRIMARY KEY(from_month) alone, i.e. one global income figure.
    # Rebuild with a surrogate id and (user_id, from_month) unique, same pattern as
    # portfolio_snapshots/portfolio_plan in the previous revision.
    with op.batch_alter_table("budget_history", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"))
    op.execute("UPDATE budget_history SET id = rowid WHERE id IS NULL")
    with op.batch_alter_table("budget_history", recreate="always") as batch_op:
        batch_op.alter_column("id", nullable=False)
        batch_op.create_primary_key("pk_budget_history", ["id"])
        batch_op.create_unique_constraint("uq_budget_history_user_month", ["user_id", "from_month"])

    # settings: was a singleton row (PRIMARY KEY id, CHECK (id = 1)). Rekey on user_id so each
    # user gets their own row; the existing row becomes user 1's settings.
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE settings SET user_id = id WHERE user_id IS NULL")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Present only if this db was previously downgraded past this revision (the downgrade
    # re-adds it by name); a fresh upgrade's unnamed original CHECK is dropped silently by
    # the batch recreate itself. Drop it explicitly if present so it isn't carried into the
    # new table after `id` (the column it checks) is gone.
    has_named_check = any(
        ck.get("name") == "settings_id_check" for ck in inspector.get_check_constraints("settings")
    )
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.alter_column("user_id", nullable=False)
        if has_named_check:
            batch_op.drop_constraint("settings_id_check", type_="check")
        batch_op.drop_column("id")
        batch_op.create_primary_key("pk_settings", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))
    op.execute("UPDATE settings SET id = user_id WHERE id IS NULL")
    with op.batch_alter_table("settings", recreate="always") as batch_op:
        batch_op.alter_column("id", nullable=False)
        batch_op.drop_column("user_id")
        batch_op.create_primary_key("pk_settings", ["id"])
        batch_op.create_check_constraint("settings_id_check", "id = 1")

    with op.batch_alter_table("budget_history", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_budget_history_user_month", type_="unique")
        batch_op.drop_column("user_id")
        batch_op.drop_column("id")
        batch_op.create_primary_key("pk_budget_history", ["from_month"])
