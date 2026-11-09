"""add MF Analysis tables: imported factsheet files, one row per fund per month, and the fund's holdings

Revision ID: e9a2b4c6d8f0
Revises: d8f1a3c5e7b9
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.ddl import now_text, table_names


# revision identifiers, used by Alembic.
revision: str = 'e9a2b4c6d8f0'
down_revision: Union[str, Sequence[str], None] = 'd8f1a3c5e7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FLOATS = ("aum_cr", "ter_pct", "std_dev", "beta", "sharpe", "alpha", "treynor", "turnover_pct", "top10_pct", "cash_pct",
          "cap_large", "cap_mid", "cap_small", "ret_1y", "ret_3y", "ret_5y", "bench_1y", "bench_3y", "bench_5y",
          "ytm", "mod_duration", "avg_maturity", "macaulay", "credit_aaa_sov_pct")


def _uid():
    return sa.Column("user_id", sa.Integer(), nullable=False, server_default="1")


def _text(name):
    return sa.Column(name, sa.String(), nullable=False, server_default="")


def upgrade() -> None:
    bind = op.get_bind()
    have = table_names(bind)
    if "mf_sources" not in have:
        op.create_table(
            "mf_sources",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            _text("sha256"), sa.Column("kind", sa.String(), nullable=False, server_default="factsheet"), _text("amc"),
            sa.Column("funds", sa.Integer(), nullable=False, server_default="0"), _text("notes"),
            sa.Column("imported_at", sa.String(), nullable=False, server_default=now_text(bind)),
            sa.UniqueConstraint("user_id", "month", "file_name"),
        )
    if "mf_fund_months" not in have:
        op.create_table(
            "mf_fund_months",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("scheme_key", sa.String(), nullable=False),
            sa.Column("scheme", sa.String(), nullable=False),
            _text("plan"), _text("amc"), _text("amfi_code"), _text("category"), _text("benchmark"),
            *[sa.Column(c, sa.Float(), nullable=True) for c in FLOATS],
            sa.Column("managers", sa.Text(), nullable=False, server_default=""),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("user_id", "scheme_key", "month"),
        )
    if "mf_holdings" not in have:
        op.create_table(
            "mf_holdings",
            sa.Column("id", sa.Integer(), primary_key=True), _uid(),
            sa.Column("fund_month_id", sa.Integer(), sa.ForeignKey("mf_fund_months.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            _text("isin"), sa.Column("pct", sa.Float(), nullable=False, server_default="0"), _text("sector"), _text("rating"),
        )
        op.create_index("ix_mf_holdings_fund_month", "mf_holdings", ["fund_month_id"])
        op.create_index("ix_mf_holdings_user", "mf_holdings", ["user_id"])


def downgrade() -> None:
    have = table_names(op.get_bind())
    if "mf_holdings" in have:
        op.drop_index("ix_mf_holdings_user", table_name="mf_holdings")
        op.drop_index("ix_mf_holdings_fund_month", table_name="mf_holdings")
        op.drop_table("mf_holdings")
    for t in ("mf_fund_months", "mf_sources"):
        if t in have:
            op.drop_table(t)
