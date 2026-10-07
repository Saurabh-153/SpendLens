"""Expense domain: categories, their monthly targets, budget history, expenses, subcategories
and the auto-categorisation rules. Mirrors the tables database.py created by hand.
"""
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    icon: Mapped[str] = mapped_column(default="\U0001F4E6")
    color: Mapped[str] = mapped_column(default="#64748b")
    target_pct: Mapped[int] = mapped_column(default=0)
    hint: Mapped[str] = mapped_column(default="")
    visible: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=99)
    start_month: Mapped[str] = mapped_column(default="0000-00")
    end_month: Mapped[str] = mapped_column(nullable=True)


class CategoryTarget(Base):
    """Child of Category; scoped to a user through category_id -> categories.user_id, so no
    user_id column of its own."""
    __tablename__ = "category_targets"

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True)
    from_month: Mapped[str] = mapped_column(primary_key=True)
    target_pct: Mapped[int] = mapped_column(default=0)


class BudgetHistory(Base):
    """Was PRIMARY KEY(from_month) alone, i.e. one global income/savings figure. Each user's
    income differs, so this gets a user_id ahead of multi-user, same as the portfolio tables."""
    __tablename__ = "budget_history"
    __table_args__ = (UniqueConstraint("user_id", "from_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    from_month: Mapped[str]
    income: Mapped[int]
    savings_amount: Mapped[float] = mapped_column(nullable=True)


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    user_id: Mapped[int] = mapped_column(default=1)
    date: Mapped[str]
    amount: Mapped[float]
    note: Mapped[str] = mapped_column(default="")
    cashback: Mapped[float] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default="")
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id"), nullable=True)


class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    sort_order: Mapped[int] = mapped_column(default=99)
    start_month: Mapped[str] = mapped_column(default="0000-00")
    end_month: Mapped[str] = mapped_column(nullable=True)


class SubcategoryRule(Base):
    __tablename__ = "subcategory_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    user_id: Mapped[int] = mapped_column(default=1)
    pattern: Mapped[str]
    match_type: Mapped[str] = mapped_column(default="contains")
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id"))


class Settings(Base):
    """Was a singleton row (PRIMARY KEY id, CHECK (id = 1)) — one settings row for the whole
    app. Multi-user means one settings row per user instead, so user_id becomes the key."""
    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(primary_key=True, default=1)
    income: Mapped[int] = mapped_column(default=245000)
    savings_target: Mapped[int] = mapped_column(default=44)
    currency: Mapped[str] = mapped_column(default="INR")
    fiscal_year_start: Mapped[str] = mapped_column(default="April")
    date_format: Mapped[str] = mapped_column(default="DD/MM/YYYY")
    price_source: Mapped[str] = mapped_column(default="Manual Entry")
    auto_refresh: Mapped[str] = mapped_column(default="Disabled (manual)")
