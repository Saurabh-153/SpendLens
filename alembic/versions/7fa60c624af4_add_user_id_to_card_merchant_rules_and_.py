"""add user_id to card_merchant_rules and card_accounts

Revision ID: 7fa60c624af4
Revises: 459d2bc3ff86
Create Date: 2026-10-08 00:51:08.417256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fa60c624af4'
down_revision: Union[str, Sequence[str], None] = '459d2bc3ff86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both tables already have a plain integer id primary key, so (unlike the previous two
    # revisions) this is a straight add-column — no primary key rebuild needed.
    with op.batch_alter_table("card_accounts") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("card_merchant_rules") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("card_merchant_rules") as batch_op:
        batch_op.drop_column("user_id")
    with op.batch_alter_table("card_accounts") as batch_op:
        batch_op.drop_column("user_id")
