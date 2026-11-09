"""indexes for the per-user lookups: every query filters by user_id, and the month views by date

Revision ID: b1e3a6c8d0f2
Revises: a9d1f4b7c2e6
Create Date: 2026-10-18 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b1e3a6c8d0f2'
down_revision: Union[str, Sequence[str], None] = 'a9d1f4b7c2e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index name, table, columns). portfolio_snapshots / portfolio_plan already have (user_id, ...) unique indexes.
INDEXES = [
    ("ix_expenses_user_date", "expenses", ["user_id", "date"]),
    ("ix_expenses_category", "expenses", ["category_id"]),
    ("ix_categories_user", "categories", ["user_id"]),
    ("ix_subcategories_user_category", "subcategories", ["user_id", "category_id"]),
    ("ix_subcategory_rules_user_category", "subcategory_rules", ["user_id", "category_id"]),
    ("ix_holdings_user", "holdings", ["user_id"]),
    ("ix_transactions_user_date", "transactions", ["user_id", "tx_date"]),
    ("ix_cards_user", "cards", ["user_id"]),
    ("ix_card_accounts_user", "card_accounts", ["user_id"]),
    ("ix_reminders_user", "reminders", ["user_id"]),
    ("ix_trackers_user", "trackers", ["user_id"]),
    ("ix_auth_sessions_user", "auth_sessions", ["user_id"]),
    ("ix_auth_sessions_expires", "auth_sessions", ["expires_at"]),
    ("ix_access_requests_status", "access_requests", ["status", "user_id"]),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
