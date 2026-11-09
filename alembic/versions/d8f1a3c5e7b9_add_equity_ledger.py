"""add the stock ledger: broker trades, corporate actions, dividends, holdings statements, securities and an audit log

Revision ID: d8f1a3c5e7b9
Revises: c7e2f9a4b1d3
Create Date: 2026-11-07 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text, table_names


# revision identifiers, used by Alembic.
revision: str = 'd8f1a3c5e7b9'
down_revision: Union[str, Sequence[str], None] = 'c7e2f9a4b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("equity_trades", "equity_events", "equity_dividends", "broker_holdings", "equity_securities", "equity_audit")
USER_INDEXED = ("equity_events", "broker_holdings", "equity_audit")   # the others lead with user_id in a unique key or index


def _uid():
    return sa.Column("user_id", sa.Integer(), nullable=False, server_default="1")


def upgrade() -> None:
    bind = op.get_bind()
    have = table_names(bind)
    if "equity_trades" not in have:
        op.create_table(
            "equity_trades",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("account", sa.String(), nullable=False),
            sa.Column("client_id", sa.String(), nullable=False, server_default=""),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("isin", sa.String(), nullable=False, server_default=""),
            sa.Column("trade_date", sa.String(), nullable=False),
            sa.Column("side", sa.String(), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("exchange", sa.String(), nullable=False, server_default=""),
            sa.Column("trade_id", sa.String(), nullable=False, server_default=""),
            sa.Column("order_id", sa.String(), nullable=False, server_default=""),
            sa.Column("executed_at", sa.String(), nullable=False, server_default=""),
            sa.Column("fingerprint", sa.String(), nullable=False),
            sa.Column("import_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("user_id", "fingerprint"),
        )
        op.create_index("ix_equity_trades_user_date", "equity_trades", ["user_id", "trade_date"])
    if "equity_events" not in have:
        op.create_table(
            "equity_events",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("account", sa.String(), nullable=False, server_default=""),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("ex_date", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("ratio_new", sa.Float(), nullable=False, server_default="0"),
            sa.Column("ratio_old", sa.Float(), nullable=False, server_default="0"),
            sa.Column("qty", sa.Float(), nullable=False, server_default="0"),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("target_symbol", sa.String(), nullable=False, server_default=""),
            sa.Column("cost_pct", sa.Float(), nullable=False, server_default="0"),
            sa.Column("note", sa.String(), nullable=False, server_default=""),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.String(), nullable=False, server_default=now_text(bind)),
        )
    if "equity_dividends" not in have:
        op.create_table(
            "equity_dividends",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("account", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("ex_date", sa.String(), nullable=False),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("dps", sa.Float(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="zerodha"),
            sa.Column("raw_symbol", sa.String(), nullable=False, server_default=""),
            sa.Column("import_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=False, server_default=now_text(bind)),
            sa.UniqueConstraint("user_id", "account", "symbol", "ex_date", "dps", "source"),
        )
    if "broker_holdings" not in have:
        op.create_table(
            "broker_holdings",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("account", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("isin", sa.String(), nullable=False, server_default=""),
            sa.Column("qty", sa.Float(), nullable=False),
            sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("as_of", sa.String(), nullable=False),
            sa.Column("import_id", sa.Integer(), nullable=True),
        )
    if "equity_securities" not in have:
        op.create_table(
            "equity_securities",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("yahoo_symbol", sa.String(), nullable=False, server_default=""),
            sa.Column("name", sa.String(), nullable=False, server_default=""),
            sa.Column("last_price", sa.Float(), nullable=True),
            sa.Column("price_date", sa.String(), nullable=False, server_default=""),
            sa.Column("fetch_error", sa.String(), nullable=False, server_default=""),
            sa.UniqueConstraint("user_id", "symbol"),
        )
    if "equity_audit" not in have:
        op.create_table(
            "equity_audit",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("at", sa.String(), nullable=False, server_default=now_text(bind)),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("account", sa.String(), nullable=False, server_default=""),
            sa.Column("file_name", sa.String(), nullable=False, server_default=""),
            sa.Column("period_from", sa.String(), nullable=False, server_default=""),
            sa.Column("period_to", sa.String(), nullable=False, server_default=""),
            sa.Column("summary", sa.String(), nullable=False, server_default=""),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        )
    have_idx = {t: {i["name"] for i in sa.inspect(bind).get_indexes(t)} for t in USER_INDEXED}
    for t in USER_INDEXED:
        if f"ix_{t}_user" not in have_idx[t]:
            op.create_index(f"ix_{t}_user", t, ["user_id"])


def downgrade() -> None:
    have = table_names(op.get_bind())
    if "equity_trades" in have:
        op.drop_index("ix_equity_trades_user_date", table_name="equity_trades")
    for t in USER_INDEXED:
        if t in have:
            op.drop_index(f"ix_{t}_user", table_name=t)
    for t in reversed(TABLES):
        if t in have:
            op.drop_table(t)
