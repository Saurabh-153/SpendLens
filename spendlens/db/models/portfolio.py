"""Portfolio domain: holdings, their groups, daily snapshots (portfolio-wide and per-holding),
goals and the mix/plan key-value store. Mirrors the tables `database.py`/`portfolio.py` created
by hand; column names and defaults are kept identical so existing data reads unchanged.
"""
from typing import Optional

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    ticker: Mapped[str] = mapped_column(default="")
    asset_type: Mapped[str] = mapped_column(default="EQ")
    sector: Mapped[str] = mapped_column(default="")
    qty: Mapped[float] = mapped_column(default=0)
    buy_price: Mapped[float] = mapped_column(default=0)
    cmp: Mapped[float] = mapped_column(default=0)
    week52_low: Mapped[float] = mapped_column(default=0)
    week52_high: Mapped[float] = mapped_column(default=0)
    notes: Mapped[str] = mapped_column(default="")
    visible: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default="")
    grp: Mapped[str] = mapped_column(default="")
    sip_amount: Mapped[float] = mapped_column(default=0)
    maturity: Mapped[str] = mapped_column(default="")
    sip_day: Mapped[int] = mapped_column(default=0)
    sip_applied: Mapped[str] = mapped_column(default="")
    rate: Mapped[float] = mapped_column(default=0)
    start_date: Mapped[str] = mapped_column(default="")
    compounding: Mapped[str] = mapped_column(default="Q")
    rd: Mapped[int] = mapped_column(default=0)
    credits: Mapped[str] = mapped_column(default="")
    manual: Mapped[int] = mapped_column(default=0)
    scheme_code: Mapped[str] = mapped_column(default="")
    units: Mapped[float] = mapped_column(default=0)
    nav: Mapped[float] = mapped_column(default=0)
    auto_price: Mapped[int] = mapped_column(default=0)
    price_date: Mapped[str] = mapped_column(default="")
    price_note: Mapped[str] = mapped_column(default="")
    tags: Mapped[str] = mapped_column(default="")
    exposure: Mapped[str] = mapped_column(default="")
    sip_reminder: Mapped[int] = mapped_column(default=1, server_default="1")


class HoldingGroup(Base):
    __tablename__ = "holding_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = mapped_column(unique=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    hidden_columns: Mapped[str] = mapped_column(default="")


class PortfolioSnapshot(Base):
    """One row per user per day: total/invested value plus a JSON blob of per-group totals.
    Written once a day by investing_routes.refresh_and_snapshot, overwritten on re-run same day."""
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "snap_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    snap_date: Mapped[str]
    total: Mapped[float] = mapped_column(nullable=True)
    invested: Mapped[float] = mapped_column(nullable=True)
    groups: Mapped[str] = mapped_column(nullable=True)


class HoldingSnapshot(Base):
    """One row per holding per day: lets a holding's value be charted over time, which the live
    `holdings` row (overwritten on every price refresh) can't do on its own."""
    __tablename__ = "holding_snapshots"
    __table_args__ = (UniqueConstraint("holding_id", "snap_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("holdings.id"))
    snap_date: Mapped[str]
    qty: Mapped[float] = mapped_column(nullable=True)
    cmp: Mapped[float] = mapped_column(nullable=True)
    present: Mapped[float] = mapped_column(nullable=True)
    invested: Mapped[float] = mapped_column(nullable=True)


class PortfolioGoal(Base):
    __tablename__ = "portfolio_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    target_amount: Mapped[float]
    target_year: Mapped[int]


class PortfolioPlan(Base):
    """Key/value store for mix targets, return assumptions etc. (portfolio.py's get_plan/set_plan)."""
    __tablename__ = "portfolio_plan"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    key: Mapped[str]
    value: Mapped[str] = mapped_column(nullable=True)


# The tables below predate the ORM. Columns are declared in the existing tables' order, because
# routes return their rows as dicts and the key order is part of the API's JSON.

class SipLog(Base):
    """One row per SIP instalment applied to a holding (sip.py)."""
    __tablename__ = "sip_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[Optional[int]]
    holding_name: Mapped[Optional[str]]
    month: Mapped[Optional[str]]
    sip_date: Mapped[Optional[str]]
    amount: Mapped[Optional[float]]
    applied_at: Mapped[Optional[str]]
    user_id: Mapped[Optional[int]] = mapped_column(default=1)


class LedgerTransaction(Base):
    """Investment ledger: buys, sells, dividends and opening balances (ledger.py)."""
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[Optional[int]]
    name: Mapped[Optional[str]] = mapped_column(default="")
    tx_date: Mapped[str]
    kind: Mapped[str]
    qty: Mapped[Optional[float]] = mapped_column(default=0)
    price: Mapped[Optional[float]] = mapped_column(default=0)
    amount: Mapped[Optional[float]] = mapped_column(default=0)
    fees: Mapped[Optional[float]] = mapped_column(default=0)
    realized: Mapped[Optional[float]] = mapped_column(default=0)
    note: Mapped[Optional[str]] = mapped_column(default="")
    source: Mapped[Optional[str]] = mapped_column(default="manual")
    applied: Mapped[Optional[int]] = mapped_column(default=0)
    user_id: Mapped[Optional[int]] = mapped_column(default=1)


class PriceRun(Base):
    """Log of price refreshes (prices.py)."""
    __tablename__ = "price_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ran_at: Mapped[Optional[str]]
    ok: Mapped[Optional[int]]
    updated: Mapped[Optional[int]]
    failed: Mapped[Optional[int]]
    detail: Mapped[Optional[str]]


class PriceHistory(Base):
    """Closing price / NAV per holding per day."""
    __tablename__ = "price_history"

    holding_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    price_date: Mapped[str] = mapped_column(primary_key=True)
    price: Mapped[Optional[float]]


class AppPref(Base):
    """Small app-wide key/value settings (e.g. the Holdings table's column layout)."""
    __tablename__ = "app_prefs"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(default="")
