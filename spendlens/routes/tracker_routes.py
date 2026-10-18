"""Day trackers (gym day, office day, ...) on the reminder calendar: CRUD, ticking a day, and the month KPIs the
calendar shows above the grid.

Weeks are Monday-start rows clipped to the month. A tracker counts on its weekdays; a day is paused (no goal) when a
vacation covers it or a public holiday falls on it, for whichever of those the tracker's `pause_on` lists. A week's goal
is the weekly target scaled to the scheduled days that week, so month edges, holidays and vacations lower it.
"""
import calendar
import math
import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func

from db.engine import get_session
from db.models import Category, Expense, Reminder, Subcategory, Tracker, TrackerCostLink, TrackerDay
from .reminder_routes import USER_ID, _bad, _clean_color, _clean_name, _falls_in, _month_holidays, _month_vacations, _parse_today

router = APIRouter(prefix="/spendlens/api", tags=["trackers"])

ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]
PAUSE_REASONS = ("vacation", "IN", "US")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _half_up(x):
    return int(math.floor(x + 0.5))


def _csv_ints(text):
    return [int(p) for p in (text or "").split(",") if p.strip() != ""]


def _csv(text):
    return [p for p in (text or "").split(",") if p]


# ---------------------------------------------------------------- CRUD

class CostLink(BaseModel):
    category_id: int
    subcategory_id: Optional[int] = None


class TrackerCreate(BaseModel):
    name: str
    color: str = "#7a52d6"
    target_per_week: int = 3
    weekdays: List[int] = ALL_WEEKDAYS
    pause_on: List[str] = ["vacation"]
    bill_reminder_id: Optional[int] = None
    cost_links: List[CostLink] = []


class TrackerUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    target_per_week: Optional[int] = None
    weekdays: Optional[List[int]] = None
    pause_on: Optional[List[str]] = None
    bill_reminder_id: Optional[int] = None
    cost_links: Optional[List[CostLink]] = None


class Reorder(BaseModel):
    ids: List[int]


class DayTick(BaseModel):
    done: bool


def _links(session, tid):
    return session.query(TrackerCostLink).filter(TrackerCostLink.tracker_id == tid).order_by(TrackerCostLink.id).all()


def _tracker_view(session, t):
    return {"id": t.id, "name": t.name, "color": t.color, "target_per_week": t.target_per_week,
            "weekdays": _csv_ints(t.weekdays), "pause_on": _csv(t.pause_on), "bill_reminder_id": t.bill_reminder_id,
            "cost_links": [{"category_id": l.expense_category_id, "subcategory_id": l.expense_subcategory_id} for l in _links(session, t.id)],
            "sort_order": t.sort_order}


def _tracker_or_404(session, tid):
    t = session.get(Tracker, tid)
    if not t or t.user_id != USER_ID:
        _bad("Tracker not found", 404)
    return t


def _clean_target(v):
    if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 7:
        _bad("target_per_week must be between 1 and 7")
    return v


def _clean_weekdays(v):
    days = sorted(set(v))
    if not days or any(not isinstance(d, int) or not 0 <= d <= 6 for d in days):
        _bad("weekdays must be a non-empty list of 0 (Monday) to 6 (Sunday)")
    return ",".join(str(d) for d in days)


def _clean_pause(v):
    bad = [p for p in v if p not in PAUSE_REASONS]
    if bad:
        _bad("pause_on may only contain vacation, IN and US")
    return ",".join(p for p in PAUSE_REASONS if p in v)


def _clean_bill(session, rid):
    if rid is None:
        return None
    r = session.get(Reminder, rid)
    if not r or r.user_id != USER_ID:
        _bad("bill_reminder_id: reminder not found")
    return rid


def _clean_links(session, links):
    out = []
    for l in links:
        if not session.get(Category, l.category_id):
            _bad("cost_links: expense category not found")
        if l.subcategory_id is not None:
            sub = session.get(Subcategory, l.subcategory_id)
            if not sub:
                _bad("cost_links: expense sub-category not found")
            if sub.category_id != l.category_id:
                _bad("cost_links: sub-category does not belong to that expense category")
        pair = (l.category_id, l.subcategory_id)
        if pair not in out:
            out.append(pair)
    return out


def _set_links(session, tid, pairs):
    session.query(TrackerCostLink).filter(TrackerCostLink.tracker_id == tid).delete(synchronize_session=False)
    for cid, sid in pairs:
        session.add(TrackerCostLink(tracker_id=tid, expense_category_id=cid, expense_subcategory_id=sid))


@router.get("/trackers")
def list_trackers(session=Depends(get_session)):
    rows = session.query(Tracker).filter(Tracker.user_id == USER_ID).order_by(Tracker.sort_order, Tracker.id).all()
    return [_tracker_view(session, t) for t in rows]


@router.post("/trackers", status_code=201)
def create_tracker(data: TrackerCreate, session=Depends(get_session)):
    values = dict(name=_clean_name(data.name), color=_clean_color(data.color), target_per_week=_clean_target(data.target_per_week),
                  weekdays=_clean_weekdays(data.weekdays), pause_on=_clean_pause(data.pause_on),
                  bill_reminder_id=_clean_bill(session, data.bill_reminder_id))
    pairs = _clean_links(session, data.cost_links)
    order = (session.query(func.max(Tracker.sort_order)).filter(Tracker.user_id == USER_ID).scalar() or 0) + 1
    t = Tracker(user_id=USER_ID, sort_order=order, **values)
    session.add(t)
    session.flush()
    _set_links(session, t.id, pairs)
    session.commit()
    return _tracker_view(session, t)


# Fixed path first: /trackers/{tid} would otherwise swallow it.
@router.put("/trackers/reorder")
def reorder_trackers(data: Reorder, session=Depends(get_session)):
    rows = session.query(Tracker).filter(Tracker.user_id == USER_ID).order_by(Tracker.sort_order, Tracker.id).all()
    by_id = {t.id: t for t in rows}
    if len(set(data.ids)) != len(data.ids) or any(i not in by_id for i in data.ids):
        _bad("ids must be distinct, existing tracker ids")
    ordered = [by_id[i] for i in data.ids] + [t for t in rows if t.id not in set(data.ids)]
    for n, t in enumerate(ordered, start=1):
        t.sort_order = n
    session.commit()
    return [_tracker_view(session, t) for t in ordered]


@router.put("/trackers/{tid}")
def update_tracker(tid: int, data: TrackerUpdate, session=Depends(get_session)):
    t = _tracker_or_404(session, tid)
    given = data.model_dump(exclude_unset=True)
    for k in ("name", "color", "target_per_week", "weekdays", "pause_on", "cost_links"):
        if k in given and given[k] is None:
            _bad(f"{k} cannot be empty")
    if "name" in given:
        t.name = _clean_name(data.name)
    if "color" in given:
        t.color = _clean_color(data.color)
    if "target_per_week" in given:
        t.target_per_week = _clean_target(data.target_per_week)
    if "weekdays" in given:
        t.weekdays = _clean_weekdays(data.weekdays)
    if "pause_on" in given:
        t.pause_on = _clean_pause(data.pause_on)
    if "bill_reminder_id" in given:
        t.bill_reminder_id = _clean_bill(session, data.bill_reminder_id)
    if "cost_links" in given:
        _set_links(session, tid, _clean_links(session, data.cost_links))
    session.commit()
    return _tracker_view(session, t)


@router.delete("/trackers/{tid}")
def delete_tracker(tid: int, session=Depends(get_session)):
    t = _tracker_or_404(session, tid)
    session.query(TrackerDay).filter(TrackerDay.tracker_id == tid).delete(synchronize_session=False)
    session.query(TrackerCostLink).filter(TrackerCostLink.tracker_id == tid).delete(synchronize_session=False)
    session.delete(t)
    session.commit()
    return {"ok": True}


@router.put("/trackers/{tid}/days/{day}")
def tick_tracker_day(tid: int, day: str, data: DayTick, today: str = Query(None), session=Depends(get_session)):
    _tracker_or_404(session, tid)
    if not ISO_DATE.match(day):
        _bad("date must be YYYY-MM-DD")
    try:
        when = date.fromisoformat(day)
    except ValueError:
        _bad("date is not a real date")
    if when > _parse_today(today):
        _bad("A future day can't be ticked")
    row = session.get(TrackerDay, (tid, day))
    if data.done and row is None:
        session.add(TrackerDay(tracker_id=tid, date=day))
    elif not data.done and row is not None:
        session.delete(row)
    session.commit()
    return {"tracker_id": tid, "date": day, "done": data.done}


# ---------------------------------------------------------------- month KPIs (used by GET /reminders/calendar)

def month_trackers(session, y, mon, today, holidays=None, vacations=None):
    """Every tracker with its ticks, scheduled days and KPIs for one month."""
    trackers = session.query(Tracker).filter(Tracker.user_id == USER_ID).order_by(Tracker.sort_order, Tracker.id).all()
    if not trackers:
        return []
    n_days = calendar.monthrange(y, mon)[1]
    prefix = f"{y:04d}-{mon:02d}-"
    holidays = _month_holidays(y, mon) if holidays is None else holidays
    vacations = _month_vacations(session, y, mon) if vacations is None else vacations
    hol_days = {c: {h["day"] for h in holidays if h["country"] == c} for c in ("IN", "US")}
    vac_days = {d for d in range(1, n_days + 1) for v in vacations if v["start_date"] <= f"{prefix}{d:02d}" <= v["end_date"]}

    ticks = {}
    for tid, d in session.query(TrackerDay.tracker_id, TrackerDay.date).filter(TrackerDay.date.like(f"{prefix}%")):
        ticks.setdefault(tid, set()).add(int(d[8:10]))

    first_wd = date(y, mon, 1).weekday()
    week_of = {d: (first_wd + d - 1) // 7 for d in range(1, n_days + 1)}
    n_weeks = week_of[n_days] + 1
    month_start, month_end = date(y, mon, 1), date(y, mon, n_days)
    elapsed = {d for d in range(1, n_days + 1) if date(y, mon, d) <= today}
    if month_start <= today <= month_end:
        cur_week = week_of[today.day]
    elif today > month_end:
        cur_week = n_weeks  # every week of the month is complete
    else:
        cur_week = -1  # nothing complete yet
    this_week = (week_of[today.day] if month_start <= today <= month_end else n_weeks - 1 if today > month_end else 0)

    spend_by_day = None
    out = []
    for t in trackers:
        weekdays, pause = _csv_ints(t.weekdays), set(_csv(t.pause_on))
        def paused(d):
            return ("vacation" in pause and d in vac_days) or any(c in pause and d in hol_days[c] for c in ("IN", "US"))
        scheduled = [d for d in range(1, n_days + 1) if date(y, mon, d).weekday() in weekdays and not paused(d)]
        done = sorted(ticks.get(t.id, set()))
        sched_set, done_set = set(scheduled), set(done)

        per_week, expected = [], 0.0
        for w in range(n_weeks):
            days = [d for d in range(1, n_days + 1) if week_of[d] == w]
            sw = [d for d in days if d in sched_set]
            goal = _half_up(t.target_per_week * len(sw) / len(weekdays))
            if sw:
                expected += goal * (len([d for d in sw if d in elapsed]) / len(sw))
            per_week.append({"start_day": days[0], "end_day": days[-1], "done": len([d for d in days if d in done_set]), "goal": goal})

        count = len(done)
        expected = round(expected, 2)
        if expected == 0 or count / expected >= 1:
            status = "good"
        elif count / expected >= 0.8:
            status = "warn"
        else:
            status = "bad"
        elapsed_sched = len([d for d in scheduled if d in elapsed])
        projected = count if elapsed_sched == 0 else max(count, _half_up(count / elapsed_sched * len(scheduled)))

        complete = [w for i, w in enumerate(per_week) if i < cur_week and w["goal"] > 0]
        on_target = [w["done"] >= w["goal"] for w in complete]
        streak = 0
        for ok in reversed(on_target):
            if not ok:
                break
            streak += 1

        cost = None
        links = _links(session, t.id)
        if links:
            if spend_by_day is None:
                spend_by_day = session.query(Expense.date, Expense.category_id, Expense.subcategory_id, Expense.amount) \
                    .filter(Expense.date.like(f"{prefix}%")).all()
            pairs = [(l.expense_category_id, l.expense_subcategory_id) for l in links]
            daily = {}
            for d, cid, sid, amount in spend_by_day:
                if any(cid == lc and (ls is None or sid == ls) for lc, ls in pairs):
                    daily[int(d[8:10])] = daily.get(int(d[8:10]), 0.0) + amount
            on = [daily.get(d, 0.0) for d in scheduled if d in elapsed and d in done_set]
            off = [daily.get(d, 0.0) for d in scheduled if d in elapsed and d not in done_set]
            if on and off:
                avg_on, avg_off = sum(on) / len(on), sum(off) / len(off)
                cost = {"avg_on": round(avg_on, 2), "avg_off": round(avg_off, 2), "n_on": len(on), "n_off": len(off),
                        "diff": _half_up(avg_on - avg_off)}

        cost_per_visit = None
        if t.bill_reminder_id is not None and count > 0:
            bill = session.get(Reminder, t.bill_reminder_id)
            if bill and bill.enabled and _falls_in(bill, mon):
                cost_per_visit = {"bill_name": bill.name, "amount": bill.amount, "per_visit": _half_up(bill.amount / count)}

        out.append({"id": t.id, "name": t.name, "color": t.color, "target_per_week": t.target_per_week, "weekdays": weekdays,
                    "pause_on": _csv(t.pause_on), "done_days": done, "scheduled_days": scheduled,
                    "kpi": {"count": count, "month_goal": sum(w["goal"] for w in per_week), "expected_by_today": expected,
                            "projected": projected, "status": status,
                            "this_week": {"done": per_week[this_week]["done"], "goal": per_week[this_week]["goal"]},
                            "weeks_on_target": sum(on_target), "complete_weeks": len(complete), "week_streak": streak,
                            "per_week": per_week, "cost": cost, "cost_per_visit": cost_per_visit}})
    return out
