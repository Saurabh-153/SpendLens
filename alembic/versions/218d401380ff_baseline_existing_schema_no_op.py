"""baseline: existing schema, no-op

Every table up to and including this revision was created by database.py's hand-rolled
MIGRATIONS list (raw sqlite3), before Alembic existed in this project. This revision does
nothing — it just gives Alembic a starting point to stamp the live database at, so later
revisions (which DO run real DDL) apply only the new changes on top of what's already there.

Revision ID: 218d401380ff
Revises:
Create Date: 2026-10-08 00:39:12.256135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '218d401380ff'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
