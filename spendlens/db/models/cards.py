"""Cards domain: cards, their statements/transactions/perks, merchant auto-classification
rules, and the issuer accounts a card belongs to. Mirrors the tables database.py created
by hand.
"""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CardAccount(Base):
    """Didn't carry a user_id before multi-user; nothing scoped it to anyone."""
    __tablename__ = "card_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    issuer: Mapped[str] = mapped_column(default="")
    label: Mapped[str] = mapped_column(default="")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    issuer: Mapped[str] = mapped_column(default="")
    network: Mapped[str] = mapped_column(default="")
    last4: Mapped[str] = mapped_column(default="")
    credit_limit: Mapped[float] = mapped_column(default=0)
    cash_limit: Mapped[float] = mapped_column(default=0)
    statement_day: Mapped[int] = mapped_column(default=0)
    due_day: Mapped[int] = mapped_column(default=0)
    annual_fee: Mapped[float] = mapped_column(default=0)
    fee_waiver_spend: Mapped[float] = mapped_column(default=0)
    rate_online: Mapped[float] = mapped_column(default=0)
    rate_offline: Mapped[float] = mapped_column(default=0)
    cashback_cap: Mapped[float] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="active")
    notes: Mapped[str] = mapped_column(default="")
    profile: Mapped[str] = mapped_column(default="generic")
    rates: Mapped[str] = mapped_column(default="{}")
    grace_days: Mapped[int] = mapped_column(default=20)
    pay_buffer_days: Mapped[int] = mapped_column(default=1)
    float_rate: Mapped[float] = mapped_column(default=7)
    cycle_verified: Mapped[int] = mapped_column(default=0)
    account_id: Mapped[int] = mapped_column(ForeignKey("card_accounts.id"), nullable=True)
    perks_seeded: Mapped[int] = mapped_column(default=0)
    color: Mapped[str] = mapped_column(default="")
    sort_order: Mapped[int] = mapped_column(default=0)


class CardStatement(Base):
    """Scoped to a user through card_id -> cards.user_id, no user_id column of its own."""
    __tablename__ = "card_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    period_from: Mapped[str] = mapped_column(nullable=True)
    period_to: Mapped[str]
    stmt_date: Mapped[str] = mapped_column(nullable=True)
    due_date: Mapped[str] = mapped_column(nullable=True)
    total_due: Mapped[float] = mapped_column(default=0)
    min_due: Mapped[float] = mapped_column(default=0)
    purchases: Mapped[float] = mapped_column(default=0)
    credits: Mapped[float] = mapped_column(default=0)
    fees: Mapped[float] = mapped_column(default=0)
    available_credit: Mapped[float] = mapped_column(default=0)
    cashback_reported: Mapped[float] = mapped_column(nullable=True)
    cashback_calc: Mapped[float] = mapped_column(nullable=True)
    file: Mapped[str] = mapped_column(default="")
    imported_at: Mapped[str] = mapped_column(default="")
    kind: Mapped[str] = mapped_column(default="cycle")
    points_earned: Mapped[int] = mapped_column(nullable=True)
    points_balance: Mapped[int] = mapped_column(nullable=True)


class CardTxn(Base):
    """Scoped to a user through card_id -> cards.user_id, no user_id column of its own."""
    __tablename__ = "card_txns"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    statement_id: Mapped[int] = mapped_column(ForeignKey("card_statements.id"), nullable=True)
    row_hash: Mapped[str] = mapped_column(unique=True)
    tx_date: Mapped[str]
    detail: Mapped[str] = mapped_column(default="")
    merchant: Mapped[str] = mapped_column(default="")
    city: Mapped[str] = mapped_column(default="")
    amount: Mapped[float]
    dc: Mapped[str] = mapped_column(default="D")
    emi: Mapped[int] = mapped_column(default=0)
    is_spend: Mapped[int] = mapped_column(default=1)
    cls: Mapped[str] = mapped_column(default="")
    cashback: Mapped[float] = mapped_column(default=0)
    capped: Mapped[int] = mapped_column(default=0)
    kind: Mapped[str] = mapped_column(default="")
    ref: Mapped[str] = mapped_column(default="")
    ccy: Mapped[str] = mapped_column(default="")
    points: Mapped[int] = mapped_column(default=0)
    category: Mapped[str] = mapped_column(default="")


class CardMerchantRule(Base):
    """card_id NULL means "every card" — under multi-user that has to mean every card
    *of this user*, so (unlike card_statements/card_txns/card_perks) this needs its own
    user_id rather than relying solely on the card_id FK."""
    __tablename__ = "card_merchant_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=True)
    pattern: Mapped[str]
    match_type: Mapped[str] = mapped_column(default="contains")
    cls: Mapped[str]
    created_at: Mapped[str] = mapped_column(default="")


class CardPerk(Base):
    """Scoped to a user through card_id -> cards.user_id, no user_id column of its own."""
    __tablename__ = "card_perks"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    kind: Mapped[str] = mapped_column(default="other")
    title: Mapped[str]
    detail: Mapped[str] = mapped_column(default="")
    value_yr: Mapped[float] = mapped_column(default=0)
    source: Mapped[str] = mapped_column(default="")
    checked: Mapped[int] = mapped_column(default=0)
    sort: Mapped[int] = mapped_column(default=0)
    updated: Mapped[str] = mapped_column(default="")
