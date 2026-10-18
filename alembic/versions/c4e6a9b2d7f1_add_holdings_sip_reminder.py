"""add holdings.sip_reminder: whether a SIP shows in reminders and the calendar feed

Revision ID: c4e6a9b2d7f1
Revises: b3d5e8a1c2f4
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e6a9b2d7f1'
down_revision: Union[str, Sequence[str], None] = 'b3d5e8a1c2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("holdings", sa.Column("sip_reminder", sa.Integer(), nullable=False, server_default="1"))
    # One-time default, changeable per SIP in Settings > Reminders: employer provident funds (typed PF, like
    # 'PF Morgan Stanley') are not SIPs the user wants reminders for; PPF and Sukanya Samriddhi (also typed PF) are.
    op.execute(
        "UPDATE holdings SET sip_reminder = 0 WHERE asset_type = 'PF' "
        "AND lower(name) NOT LIKE '%ppf%' AND lower(name) NOT LIKE '%sukanya%' AND lower(name) NOT LIKE '%ssy%'"
    )


def downgrade() -> None:
    with op.batch_alter_table("holdings") as batch_op:
        batch_op.drop_column("sip_reminder")
