"""Day trackers on the reminder calendar (gym day, office day, ...): the trackers, the days ticked, and the expense
categories whose spending a tracker's "cost of a day" KPI compares on ticked and unticked days.
"""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now_text


class Tracker(Base):
    __tablename__ = "trackers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    name: Mapped[str]
    color: Mapped[str] = mapped_column(default="#7a52d6")
    target_per_week: Mapped[int] = mapped_column(default=3)
    weekdays: Mapped[str] = mapped_column(default="0,1,2,3,4,5,6")  # csv, 0 = Monday
    pause_on: Mapped[str] = mapped_column(default="vacation")  # csv subset of vacation / IN / US
    bill_reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=utc_now_text)


class TrackerCostLink(Base):
    __tablename__ = "tracker_cost_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id", ondelete="CASCADE"))
    expense_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    expense_subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id", ondelete="CASCADE"), nullable=True)


class TrackerDay(Base):
    __tablename__ = "tracker_days"

    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[str] = mapped_column(primary_key=True)
