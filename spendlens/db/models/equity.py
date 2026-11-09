"""Stock history imported from the broker (Zerodha Console): every trade, the corporate actions that change share
counts, the dividends paid on each ex-date, and the broker's own holdings statement to reconcile against.

`account` is the user's label for a demat account ("SK", "SS"); `client_id` is the broker's id printed in the files,
kept so a file for one account cannot be imported under another. Symbols are stored as the broker printed them;
equity.py maps old names to current ones (RENAME events and a built-in alias list).
"""
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now_text


class EquityTrade(Base):
    __tablename__ = "equity_trades"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    account: Mapped[str]
    client_id: Mapped[str] = mapped_column(default="")
    symbol: Mapped[str]
    isin: Mapped[str] = mapped_column(default="")
    trade_date: Mapped[str]                       # YYYY-MM-DD
    side: Mapped[str]                             # BUY / SELL
    qty: Mapped[float]
    price: Mapped[float]
    exchange: Mapped[str] = mapped_column(default="")
    trade_id: Mapped[str] = mapped_column(default="")
    order_id: Mapped[str] = mapped_column(default="")
    executed_at: Mapped[str] = mapped_column(default="")
    fingerprint: Mapped[str]                      # account|exchange|trade id|order id|symbol|side|qty|price|date
    import_id: Mapped[Optional[int]] = mapped_column(nullable=True)


class EquityEvent(Base):
    """A corporate action or a manual correction that changes a share count outside the tradebook.

    kind: SPLIT / BONUS (ratio_new:ratio_old, e.g. 5:1 split, 1:1 bonus), BUYBACK / TRANSFER_OUT (qty leaves at price),
    IPO / TRANSFER_IN / ADJUST (qty arrives at price; no price = cost unknown), DEMERGER (target gets ratio_new per
    ratio_old held, cost_pct of the parent's cost), MERGER (holdings become target at ratio_new per ratio_old),
    RENAME (symbol is now target_symbol). account "" applies to every account (market-wide actions).
    """
    __tablename__ = "equity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    account: Mapped[str] = mapped_column(default="")
    symbol: Mapped[str]
    ex_date: Mapped[str]
    kind: Mapped[str]
    ratio_new: Mapped[float] = mapped_column(default=0)
    ratio_old: Mapped[float] = mapped_column(default=0)
    qty: Mapped[float] = mapped_column(default=0)
    price: Mapped[Optional[float]] = mapped_column(nullable=True)
    target_symbol: Mapped[str] = mapped_column(default="")
    cost_pct: Mapped[float] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(default="")
    source: Mapped[str] = mapped_column(default="manual")   # manual / yahoo / builtin
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class EquityDividend(Base):
    __tablename__ = "equity_dividends"
    __table_args__ = (UniqueConstraint("user_id", "account", "symbol", "ex_date", "dps", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    account: Mapped[str]
    symbol: Mapped[str]                           # canonical symbol (broker suffixes like "6" / "#" removed)
    ex_date: Mapped[str]
    qty: Mapped[float]
    dps: Mapped[float]
    amount: Mapped[float]
    source: Mapped[str] = mapped_column(default="zerodha")  # zerodha (statement) / yahoo (fetched)
    raw_symbol: Mapped[str] = mapped_column(default="")
    import_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    updated_at: Mapped[str] = mapped_column(default=utc_now_text)


class BrokerHolding(Base):
    """One line of the broker's holdings statement: the share count the replayed history has to match."""
    __tablename__ = "broker_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    account: Mapped[str]
    symbol: Mapped[str]
    isin: Mapped[str] = mapped_column(default="")
    qty: Mapped[float]
    avg_price: Mapped[float] = mapped_column(default=0)
    as_of: Mapped[str]
    import_id: Mapped[Optional[int]] = mapped_column(nullable=True)


class EquitySecurity(Base):
    """Per-symbol settings and the last price the refresh fetched."""
    __tablename__ = "equity_securities"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    symbol: Mapped[str]
    yahoo_symbol: Mapped[str] = mapped_column(default="")
    name: Mapped[str] = mapped_column(default="")
    last_price: Mapped[Optional[float]] = mapped_column(nullable=True)
    price_date: Mapped[str] = mapped_column(default="")
    fetch_error: Mapped[str] = mapped_column(default="")


class EquityAudit(Base):
    """What each import and refresh changed, so the history of the data itself can be traced."""
    __tablename__ = "equity_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    at: Mapped[str] = mapped_column(default=utc_now_text)
    kind: Mapped[str]                             # tradebook / dividends / holdings / refresh / event
    account: Mapped[str] = mapped_column(default="")
    file_name: Mapped[str] = mapped_column(default="")
    period_from: Mapped[str] = mapped_column(default="")
    period_to: Mapped[str] = mapped_column(default="")
    summary: Mapped[str] = mapped_column(default="")
    detail: Mapped[str] = mapped_column(default="")   # JSON
