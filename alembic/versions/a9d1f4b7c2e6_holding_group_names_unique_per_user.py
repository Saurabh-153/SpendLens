"""holding group names are unique per user, not across the whole database

Revision ID: a9d1f4b7c2e6
Revises: f7b9d2e5a0c4
Create Date: 2026-10-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9d1f4b7c2e6'
down_revision: Union[str, Sequence[str], None] = 'f7b9d2e5a0c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table(name_unique: bool):
    """holding_groups as it should look afterwards (or, with name_unique, as it was), for SQLite's table rebuild."""
    cols = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=name_unique),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("hidden_columns", sa.String(), server_default=""),
        sa.Column("user_id", sa.Integer(), server_default="1"),
    ]
    extra = [] if name_unique else [sa.UniqueConstraint("user_id", "name", name="uq_holding_groups_user_name")]
    return sa.Table("holding_groups", sa.MetaData(), *cols, *extra)


def _swap(name_unique_after: bool):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite cannot drop a constraint, so the table is rebuilt (rows copied) into the definition we want
        with op.batch_alter_table("holding_groups", copy_from=_table(name_unique_after), recreate="always"):
            pass
        return
    if name_unique_after:
        op.drop_constraint("uq_holding_groups_user_name", "holding_groups", type_="unique")
        op.create_unique_constraint("holding_groups_name_key", "holding_groups", ["name"])
    else:
        op.drop_constraint("holding_groups_name_key", "holding_groups", type_="unique")
        op.create_unique_constraint("uq_holding_groups_user_name", "holding_groups", ["user_id", "name"])


def upgrade() -> None:
    _swap(name_unique_after=False)


def downgrade() -> None:
    _swap(name_unique_after=True)
