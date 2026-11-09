"""Reminder calendar: user-defined reminder categories, the reminders themselves, and the evening
nudge setting. Card statement/due dates and SIP dates are not stored here - they are read from
`cards` and `holdings` when the calendar is built.
"""
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now_text


class ReminderCategory(Base):
    __tablename__ = "reminder_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    color: Mapped[str] = mapped_column(default="#64748b")
    # 'card' / 'sip' mark the categories automatic card and SIP dates land in; they cannot be deleted.
    kind: Mapped[str] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    category_id: Mapped[int] = mapped_column(ForeignKey("reminder_categories.id"))
    name: Mapped[str]
    amount: Mapped[float] = mapped_column(default=0)
    day: Mapped[int]
    repeat: Mapped[str] = mapped_column(default="monthly")  # monthly / quarterly / yearly
    month: Mapped[int] = mapped_column(nullable=True)  # 1-12, only for quarterly / yearly
    enabled: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str] = mapped_column(default="")
    # The expense (category, optionally sub-category) that, once logged in the month, marks it done.
    expense_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    expense_subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id", ondelete="SET NULL"), nullable=True)
    source_key: Mapped[str] = mapped_column(nullable=True)  # '<category_id>:<subcategory_id|0>' when kept from a suggestion
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class ReminderOverride(Base):
    """One month's occurrence of a reminder moved to another day (drag and drop on the calendar)."""
    __tablename__ = "reminder_overrides"
    __table_args__ = (UniqueConstraint("reminder_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"))
    month: Mapped[str]  # YYYY-MM
    day: Mapped[int]


class Vacation(Base):
    """A trip or leave period, shown as a coloured range on the calendar. Dates are inclusive ISO strings."""
    __tablename__ = "vacations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    start_date: Mapped[str]
    end_date: Mapped[str]
    color: Mapped[str] = mapped_column(default="#0f8a8a")
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class ReminderSettings(Base):
    __tablename__ = "reminder_settings"

    user_id: Mapped[int] = mapped_column(primary_key=True, default=1)
    nudge_on: Mapped[bool] = mapped_column(default=True)
    nudge_time: Mapped[str] = mapped_column(default="21:00")
