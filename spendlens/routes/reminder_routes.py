"""Reminder calendar: reminder categories, reminders, the month view the Expense page draws, repeating-expense
suggestions, the evening-nudge setting and the `.ics` feed that Apple Calendar, Outlook and Google Calendar subscribe to.

Card statement / due dates and SIP dates are not stored: they are read from `cards` and `holdings` every time.
"""
import calendar
import math
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import holidays
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func

from db.engine import get_session
from db.models import (Card, Category, Expense, Holding, Reminder, ReminderCategory, ReminderOverride, ReminderSettings, Subcategory,
                       Tracker, Vacation)
from .expense_routes import parse_month

router = APIRouter(prefix="/spendlens/api", tags=["reminders"])

USER_ID = 1
REPEATS = ("monthly", "quarterly", "yearly")
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
CLOCK = re.compile(r"^(\d{1,2}):([0-5]\d)$")
SUGGEST_WINDOW = 8
SUGGEST_MIN_MONTHS = 5


def _bad(detail, code=400):
    raise HTTPException(status_code=code, detail=detail)


def _clean_name(value, what="Name"):
    name = (value or "").strip()
    if not name:
        _bad(f"{what} is required")
    if len(name) > 120:
        _bad(f"{what} must be 120 characters or fewer")
    return name


def _clean_color(value):
    value = (value or "").strip()
    if not HEX_COLOR.match(value):
        _bad("color must be a hex colour like #f5b942")
    return value.lower()


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _shift_month(y, m, k):
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


def _clamped(y, m, day):
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


# ---------------------------------------------------------------- reminder categories

class ReminderCategoryCreate(BaseModel):
    name: str
    color: str = "#64748b"


class ReminderCategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


def _category_or_404(session, cid):
    cat = session.get(ReminderCategory, cid)
    if not cat or cat.user_id != USER_ID:
        _bad("Reminder category not found", 404)
    return cat


def _category_view(c, count):
    return {"id": c.id, "name": c.name, "color": c.color, "kind": c.kind, "sort_order": c.sort_order, "reminder_count": count}


def _reminder_count(session, cid):
    return session.query(func.count(Reminder.id)).filter(Reminder.category_id == cid, Reminder.user_id == USER_ID).scalar()


@router.get("/reminder-categories")
def list_reminder_categories(session=Depends(get_session)):
    counts = dict(session.query(Reminder.category_id, func.count(Reminder.id))
                  .filter(Reminder.user_id == USER_ID).group_by(Reminder.category_id).all())
    cats = session.query(ReminderCategory).filter(ReminderCategory.user_id == USER_ID) \
        .order_by(ReminderCategory.sort_order, ReminderCategory.id).all()
    return [_category_view(c, counts.get(c.id, 0)) for c in cats]


@router.post("/reminder-categories", status_code=201)
def create_reminder_category(data: ReminderCategoryCreate, session=Depends(get_session)):
    name, color = _clean_name(data.name), _clean_color(data.color)
    order = (session.query(func.max(ReminderCategory.sort_order)).filter(ReminderCategory.user_id == USER_ID).scalar() or 0) + 1
    cat = ReminderCategory(user_id=USER_ID, name=name, color=color, sort_order=order)
    session.add(cat)
    session.commit()
    return _category_view(cat, 0)


@router.put("/reminder-categories/{cid}")
def update_reminder_category(cid: int, data: ReminderCategoryUpdate, session=Depends(get_session)):
    cat = _category_or_404(session, cid)
    if data.name is not None:
        cat.name = _clean_name(data.name)
    if data.color is not None:
        cat.color = _clean_color(data.color)
    session.commit()
    return _category_view(cat, _reminder_count(session, cid))


@router.delete("/reminder-categories/{cid}")
def delete_reminder_category(cid: int, move_to: int = Query(None), delete_reminders: bool = Query(False),
                             session=Depends(get_session)):
    cat = _category_or_404(session, cid)
    if cat.kind:
        _bad("Card and SIP categories can be renamed or recoloured but not deleted", 409)
    if move_to is not None and delete_reminders:
        _bad("Use move_to or delete_reminders, not both")
    count = _reminder_count(session, cid)
    moved = deleted = 0
    if count:
        if move_to is None and not delete_reminders:
            _bad(f"This category has {count} reminder{'s' if count != 1 else ''}: pass move_to=<category id> or delete_reminders=true", 409)
        mine = session.query(Reminder).filter(Reminder.category_id == cid, Reminder.user_id == USER_ID)
        if move_to is not None:
            target = session.get(ReminderCategory, move_to)
            if move_to == cid or not target or target.user_id != USER_ID:
                _bad("move_to must be a different, existing reminder category", 409)
            moved = mine.update({"category_id": move_to}, synchronize_session=False)
        else:
            deleted = mine.delete(synchronize_session=False)
    session.delete(cat)
    session.commit()
    return {"ok": True, "moved": moved, "deleted_reminders": deleted}


# ---------------------------------------------------------------- reminders

class ReminderCreate(BaseModel):
    category_id: int
    name: str
    day: int
    amount: float = 0
    repeat: str = "monthly"
    month: Optional[int] = None
    enabled: bool = True
    note: str = ""
    expense_category_id: Optional[int] = None
    expense_subcategory_id: Optional[int] = None
    source_key: Optional[str] = None


class ReminderUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = None
    day: Optional[int] = None
    amount: Optional[float] = None
    repeat: Optional[str] = None
    month: Optional[int] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None
    expense_category_id: Optional[int] = None
    expense_subcategory_id: Optional[int] = None
    source_key: Optional[str] = None


FIELDS = ("category_id", "name", "amount", "day", "repeat", "month", "enabled", "note",
          "expense_category_id", "expense_subcategory_id", "source_key")
NULLABLE = {"month", "expense_category_id", "expense_subcategory_id", "source_key"}


def _reminder_view(r):
    return {"id": r.id, **{f: getattr(r, f) for f in FIELDS}}


def _validated(session, v):
    """The cleaned field values of a reminder, or a 400 saying what is wrong."""
    out = dict(v)
    out["name"] = _clean_name(v["name"])
    cat = session.get(ReminderCategory, v["category_id"])
    if not cat or cat.user_id != USER_ID:
        _bad("Reminder category not found")
    amount = v["amount"]
    if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
        _bad("amount must be zero or more")
    out["amount"] = float(amount)
    if not isinstance(v["day"], int) or not 1 <= v["day"] <= 31:
        _bad("day must be between 1 and 31")
    if v["repeat"] not in REPEATS:
        _bad("repeat must be monthly, quarterly or yearly")
    if v["repeat"] == "monthly":
        out["month"] = None
    elif not isinstance(v["month"], int) or not 1 <= v["month"] <= 12:
        _bad("month (1-12) is required for quarterly and yearly reminders")
    out["note"] = (v["note"] or "").strip()
    ec, es = v["expense_category_id"], v["expense_subcategory_id"]
    if es is not None and ec is None:
        _bad("expense_subcategory_id needs expense_category_id")
    if ec is not None and not session.get(Category, ec):
        _bad("Expense category not found")
    if es is not None:
        sub = session.get(Subcategory, es)
        if not sub:
            _bad("Expense sub-category not found")
        if sub.category_id != ec:
            _bad("Sub-category does not belong to that expense category")
    out["source_key"] = (v["source_key"] or "").strip() or None
    return out


def _reminder_or_404(session, rid):
    r = session.get(Reminder, rid)
    if not r or r.user_id != USER_ID:
        _bad("Reminder not found", 404)
    return r


@router.get("/reminders")
def list_reminders(session=Depends(get_session)):
    rows = session.query(Reminder).filter(Reminder.user_id == USER_ID).order_by(Reminder.category_id, Reminder.day, Reminder.id).all()
    return [_reminder_view(r) for r in rows]


# Fixed paths first: /reminders/{rid} would otherwise swallow them.

def _settings_view(row):
    return {"nudge_on": True if row is None else bool(row.nudge_on), "nudge_time": "21:00" if row is None else row.nudge_time}


class ReminderSettingsUpdate(BaseModel):
    nudge_on: Optional[bool] = None
    nudge_time: Optional[str] = None


@router.get("/reminders/settings")
def get_reminder_settings(session=Depends(get_session)):
    return _settings_view(session.get(ReminderSettings, USER_ID))


@router.put("/reminders/settings")
def put_reminder_settings(data: ReminderSettingsUpdate, session=Depends(get_session)):
    row = session.get(ReminderSettings, USER_ID)
    if data.nudge_time is not None:
        m = CLOCK.match(data.nudge_time.strip())
        if not m or int(m.group(1)) > 23:
            _bad("nudge_time must be HH:MM (24 hour)")
        time = f"{int(m.group(1)):02d}:{m.group(2)}"
    if row is None:
        row = ReminderSettings(user_id=USER_ID, nudge_on=True, nudge_time="21:00")
        session.add(row)
    if data.nudge_on is not None:
        row.nudge_on = data.nudge_on
    if data.nudge_time is not None:
        row.nudge_time = time
    session.commit()
    return _settings_view(row)


def _sip_view(h):
    return {"holding_id": h.id, "name": h.name, "label": _fund_label(h.name), "amount": float(h.sip_amount),
            "day": h.sip_day, "show": bool(h.sip_reminder)}


def _sip_holdings(session):
    return session.query(Holding).filter(Holding.sip_amount > 0, Holding.sip_day >= 1, Holding.sip_day <= 31)


class SipVisibility(BaseModel):
    show: bool


@router.get("/reminders/sips")
def list_reminder_sips(session=Depends(get_session)):
    """Every holding with a SIP, shown in reminders or hidden from them."""
    return [_sip_view(h) for h in sorted(_sip_holdings(session).all(), key=lambda h: (h.name, h.id))]


@router.put("/reminders/sips/{holding_id}")
def set_reminder_sip_visibility(holding_id: int, data: SipVisibility, session=Depends(get_session)):
    """Show or hide one SIP in reminders and the calendar feed. Holdings keeps applying the SIP either way."""
    h = _sip_holdings(session).filter(Holding.id == holding_id).first()
    if not h:
        _bad("That holding has no SIP", 404)
    h.sip_reminder = 1 if data.show else 0
    session.commit()
    return _sip_view(h)


# ---------------------------------------------------------------- holidays and vacations

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VACATION_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
VACATION_MAX_DAYS = 366
HOLIDAY_COUNTRIES = (("IN", holidays.India), ("US", holidays.UnitedStates))


@lru_cache(maxsize=64)
def _year_holidays(country, year):
    """Public holidays of one country and year as ((iso_date, name), ...), sorted by date."""
    cls = dict(HOLIDAY_COUNTRIES)[country]
    return tuple(sorted((d.isoformat(), name) for d, name in cls(years=year).items()))


def _month_holidays(y, mon):
    prefix = f"{y:04d}-{mon:02d}-"
    rows = [{"date": d, "day": int(d[8:10]), "country": c, "name": name}
            for c, _ in HOLIDAY_COUNTRIES for d, name in _year_holidays(c, y) if d.startswith(prefix)]
    return sorted(rows, key=lambda h: (h["date"], h["country"]))


class VacationCreate(BaseModel):
    name: str
    start_date: str
    end_date: str
    color: str = "#0f8a8a"


class VacationUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    color: Optional[str] = None


def _vacation_view(v):
    return {"id": v.id, "name": v.name, "start_date": v.start_date, "end_date": v.end_date, "color": v.color}


def _vacation_or_404(session, vid):
    v = session.get(Vacation, vid)
    if not v or v.user_id != USER_ID:
        _bad("Vacation not found", 404)
    return v


def _vacation_values(name, start, end, color):
    name = _clean_name(name)
    days = []
    for label, value in (("start_date", start), ("end_date", end)):
        if not ISO_DATE.match(value or ""):
            _bad(f"{label} must be YYYY-MM-DD")
        try:
            days.append(date.fromisoformat(value))
        except ValueError:
            _bad(f"{label} is not a real date")
    if days[1] < days[0]:
        _bad("end_date must be on or after start_date")
    if (days[1] - days[0]).days + 1 > VACATION_MAX_DAYS:
        _bad(f"A vacation can span at most {VACATION_MAX_DAYS} days")
    color = (color or "").strip()
    if not VACATION_COLOR.match(color):
        _bad("color must be a hex colour like #0f8a8a")
    return name, days[0].isoformat(), days[1].isoformat(), color.lower()


@router.get("/vacations")
def list_vacations(session=Depends(get_session)):
    rows = session.query(Vacation).filter(Vacation.user_id == USER_ID).order_by(Vacation.start_date, Vacation.id).all()
    return [_vacation_view(v) for v in rows]


@router.post("/vacations", status_code=201)
def create_vacation(data: VacationCreate, session=Depends(get_session)):
    name, start, end, color = _vacation_values(data.name, data.start_date, data.end_date, data.color)
    v = Vacation(user_id=USER_ID, name=name, start_date=start, end_date=end, color=color)
    session.add(v)
    session.commit()
    return _vacation_view(v)


@router.put("/vacations/{vid}")
def update_vacation(vid: int, data: VacationUpdate, session=Depends(get_session)):
    v = _vacation_or_404(session, vid)
    given = data.model_dump(exclude_unset=True)
    name, start, end, color = _vacation_values(given.get("name", v.name), given.get("start_date", v.start_date),
                                               given.get("end_date", v.end_date), given.get("color", v.color))
    v.name, v.start_date, v.end_date, v.color = name, start, end, color
    session.commit()
    return _vacation_view(v)


@router.delete("/vacations/{vid}")
def delete_vacation(vid: int, session=Depends(get_session)):
    session.delete(_vacation_or_404(session, vid))
    session.commit()
    return {"ok": True}


def _month_vacations(session, y, mon):
    """Vacations that overlap the month, with their full (unclipped) date range."""
    first = f"{y:04d}-{mon:02d}-01"
    last = f"{y:04d}-{mon:02d}-{calendar.monthrange(y, mon)[1]:02d}"
    rows = session.query(Vacation).filter(Vacation.user_id == USER_ID, Vacation.start_date <= last, Vacation.end_date >= first) \
        .order_by(Vacation.start_date, Vacation.id).all()
    return [_vacation_view(v) for v in rows]


def _parse_today(value):
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        _bad("today must be YYYY-MM-DD")


def _falls_in(r, mon):
    if r.repeat == "quarterly":
        return (mon - (r.month or mon)) % 3 == 0
    if r.repeat == "yearly":
        return mon == r.month
    return True


def _card_items(cards, y, mon):
    """Automatic card dates for one month: the statement day, and the payment due date (the card's own due day when
    it is set, otherwise statement day + grace days, marked as an estimate)."""
    items = []
    for c in cards:
        if c.statement_day and c.statement_day > 0:
            items.append({"key": f"card-{c.id}-stmt", "uid": f"card-{c.id}-stmt", "name": f"{c.name} statement", "amount": 0.0,
                          "day": _clamped(y, mon, c.statement_day).day, "note": "Statement date", "info": True, "estimated": False})
        if c.due_day and c.due_day > 0:
            items.append({"key": f"card-{c.id}-due", "uid": f"card-{c.id}-due", "name": f"{c.name} payment due", "amount": 0.0,
                          "day": _clamped(y, mon, c.due_day).day, "note": "Card payment due date", "info": False, "estimated": False})
        elif c.statement_day and c.statement_day > 0:
            grace = c.grace_days if c.grace_days and c.grace_days > 0 else 20
            for k in (0, -1, -2, -3):
                yy, mm = _shift_month(y, mon, k)
                due = _clamped(yy, mm, c.statement_day) + timedelta(days=grace)
                if (due.year, due.month) == (y, mon):
                    items.append({"key": f"card-{c.id}-due", "uid": f"card-{c.id}-due", "name": f"{c.name} payment due (estimated)",
                                  "amount": 0.0, "day": due.day, "info": False, "estimated": True,
                                  "note": f"Estimated: statement on the {_ord(c.statement_day)} plus {grace} days"})
                    break
    return items


_FOLIO_TAIL = re.compile(r"\s*[(\[]\s*folio\b[^)\]]*[)\]]\s*$", re.I)


def _fund_label(name):
    """A holding's fund name without its trailing '(Folio: ...)'."""
    return _FOLIO_TAIL.sub("", name or "").strip() or (name or "")


def _sip_items(session):
    """Holdings with a SIP, grouped by SIP day. `day` is the raw day of the month; callers clamp it to the month.
    The note is the full per-fund breakdown, one 'Fund ₹amount' line each; funds held under several folios are added together."""
    groups = {}
    rows = session.query(Holding).filter(Holding.sip_amount > 0, Holding.sip_day >= 1, Holding.sip_day <= 31, Holding.sip_reminder == 1).all()
    for h in sorted(rows, key=lambda h: (h.name, h.id)):  # sorted here: byte order on every dialect, not the server's collation
        groups.setdefault(h.sip_day, []).append(h)
    items = []
    for day, hs in sorted(groups.items()):
        funds = {}
        for h in hs:
            funds[_fund_label(h.name)] = funds.get(_fund_label(h.name), 0.0) + float(h.sip_amount)
        note = "\n".join(f"{label} ₹{amt:,.0f}" for label, amt in funds.items())
        items.append({"key": f"sip-{day}", "uid": f"sip-{day}", "name": next(iter(funds)) if len(funds) == 1 else f"{len(funds)} SIPs",
                      "amount": float(sum(h.sip_amount for h in hs)), "day": day, "note": note, "info": False, "estimated": False,
                      "sources": [{"holding_id": h.id, "name": h.name, "label": _fund_label(h.name), "amount": float(h.sip_amount), "day": h.sip_day} for h in hs]})
    return items


def _active_cards(session):
    return session.query(Card).filter(Card.status == "active").order_by(Card.sort_order, Card.id).all()


def _kind_categories(session):
    return {c.kind: c.id for c in session.query(ReminderCategory).filter(ReminderCategory.user_id == USER_ID, ReminderCategory.kind.isnot(None))}


@router.get("/reminders/calendar")
def reminder_calendar(month: str = Query(None), today: str = Query(None), session=Depends(get_session)):
    month, y, mon = parse_month(month)
    today = _parse_today(today)

    spent = session.query(Expense.date, Expense.category_id, Expense.subcategory_id).filter(Expense.date.like(f"{month}-%")).all()
    logged_days = sorted({int(d[8:10]) for d, _, _ in spent})
    cats_hit = {c for _, c, _ in spent}
    pairs_hit = {(c, s) for _, c, s in spent if s is not None}

    def pending(due):
        return "up" if due >= today else "unlinked"

    moved_to = dict(session.query(ReminderOverride.reminder_id, ReminderOverride.day).filter(ReminderOverride.month == month))
    out = []
    for r in session.query(Reminder).filter(Reminder.user_id == USER_ID, Reminder.enabled.is_(True)):
        if not _falls_in(r, mon):
            continue
        due = _clamped(y, mon, moved_to.get(r.id, r.day))
        if r.expense_category_id is not None:
            hit = (r.expense_category_id, r.expense_subcategory_id) in pairs_hit if r.expense_subcategory_id is not None \
                else r.expense_category_id in cats_hit
            state = "done" if hit else ("up" if due >= today else "missing")
        else:
            state = pending(due)
        out.append({"key": f"r{r.id}", "reminder_id": r.id, "category_id": r.category_id, "name": r.name, "amount": r.amount,
                    "day": due.day, "state": state, "note": r.note, "auto": False, "estimated": False, "moved": r.id in moved_to})

    kinds = _kind_categories(session)
    auto = []
    if "card" in kinds:
        auto += [(kinds["card"], i) for i in _card_items(_active_cards(session), y, mon)]
    if "sip" in kinds:
        auto += [(kinds["sip"], i) for i in _sip_items(session)]
    for cid, i in auto:
        due = _clamped(y, mon, i["day"])
        occ = {"key": i["key"], "reminder_id": None, "category_id": cid, "name": i["name"], "amount": i["amount"],
               "day": due.day, "state": "info" if i["info"] else pending(due), "note": i["note"], "auto": True,
               "estimated": i["estimated"], "moved": False}
        if "sources" in i:
            occ["sources"] = i["sources"]
        out.append(occ)

    out.sort(key=lambda o: (o["day"], o["name"].lower()))
    nudge = _settings_view(session.get(ReminderSettings, USER_ID))
    hols, vacs = _month_holidays(y, mon), _month_vacations(session, y, mon)
    from .tracker_routes import month_trackers  # tracker_routes imports helpers from this module
    return {"month": month, "today": today.isoformat(), "occurrences": out, "logged_days": logged_days,
            "nudge": {"on": nudge["nudge_on"], "time": nudge["nudge_time"]},
            "holidays": hols, "vacations": vacs, "trackers": month_trackers(session, y, mon, today, hols, vacs)}


@router.get("/reminders/suggestions")
def reminder_suggestions(session=Depends(get_session)):
    """Expenses that recur about once a month, spotted in the last 8 months of history."""
    rows = session.query(Expense.date, Expense.category_id, Expense.subcategory_id, Expense.amount).all()
    if not rows:
        return []
    months = [d[:7] for d, *_ in rows]
    first, latest = min(months), max(months)
    (ly, lm), (fy, fm) = (int(latest[:4]), int(latest[5:7])), (int(first[:4]), int(first[5:7]))
    window = min(SUGGEST_WINDOW, (ly * 12 + lm) - (fy * 12 + fm) + 1)
    in_window = {f"{yy:04d}-{mm:02d}" for yy, mm in (_shift_month(ly, lm, -k) for k in range(window))}

    groups = {}
    for d, cid, sid, amount in rows:
        if d[:7] in in_window:
            groups.setdefault((cid, sid or 0), []).append((d[:7], int(d[8:10]), amount))

    kept = {k for (k,) in session.query(Reminder.source_key).filter(Reminder.source_key.isnot(None))}
    cat_names = {c.id: c.name for c in session.query(Category)}
    sub_names = {s.id: s.name for s in session.query(Subcategory)}
    out = []
    for (cid, sid), entries in groups.items():
        seen = {m for m, _, _ in entries}
        key = f"{cid}:{sid}"
        if len(seen) < SUGGEST_MIN_MONTHS or len(entries) > len(seen) + 2 or key in kept:
            continue
        amounts = [a for _, _, a in entries]
        amount = round(statistics.median(amounts), 2)
        if amount <= 0:
            continue
        out.append({"key": key, "name": sub_names.get(sid) or cat_names.get(cid, "Expense"), "category_id": cid,
                    "subcategory_id": sid or None, "day": int(round(statistics.median(d for _, d, _ in entries))),
                    "amount": amount, "min_amount": min(amounts), "max_amount": max(amounts), "months": len(seen),
                    "window": window, "last_seen": max(seen)})
    out.sort(key=lambda s: (-s["months"], s["day"], s["name"].lower()))
    return out


@router.post("/reminders", status_code=201)
def create_reminder(data: ReminderCreate, session=Depends(get_session)):
    v = _validated(session, data.model_dump())
    r = Reminder(user_id=USER_ID, **v)
    session.add(r)
    session.commit()
    return _reminder_view(r)


@router.put("/reminders/{rid}")
def update_reminder(rid: int, data: ReminderUpdate, session=Depends(get_session)):
    r = _reminder_or_404(session, rid)
    v = {f: getattr(r, f) for f in FIELDS}
    for k, val in data.model_dump(exclude_unset=True).items():
        if val is None and k not in NULLABLE:
            _bad(f"{k} cannot be empty")
        v[k] = val
    for k, val in _validated(session, v).items():
        setattr(r, k, val)
    session.commit()
    return _reminder_view(r)


class ReminderMove(BaseModel):
    month: str
    day: int
    scope: str = "month"


@router.put("/reminders/{rid}/move")
def move_reminder(rid: int, data: ReminderMove, session=Depends(get_session)):
    """Drag and drop: move every occurrence ('all' changes the reminder's day) or only that month's ('month')."""
    r = _reminder_or_404(session, rid)
    if data.scope not in ("all", "month"):
        _bad("scope must be all or month")
    month, y, mon = parse_month(data.month)
    if not 1 <= data.day <= 31:
        _bad("day must be between 1 and 31")
    if not _falls_in(r, mon):
        _bad("This reminder does not fall in that month")
    override = session.query(ReminderOverride).filter(ReminderOverride.reminder_id == rid, ReminderOverride.month == month).first()
    if data.scope == "all":
        r.day = data.day
        if override:
            session.delete(override)
    else:
        if data.day > calendar.monthrange(y, mon)[1]:
            _bad("That month has no such day")
        if data.day == _clamped(y, mon, r.day).day:
            if override:
                session.delete(override)
        elif override:
            override.day = data.day
        else:
            session.add(ReminderOverride(reminder_id=rid, month=month, day=data.day))
    session.commit()
    return _reminder_view(r)


@router.delete("/reminders/{rid}")
def delete_reminder(rid: int, session=Depends(get_session)):
    r = _reminder_or_404(session, rid)
    session.query(ReminderOverride).filter(ReminderOverride.reminder_id == rid).delete(synchronize_session=False)
    session.query(Tracker).filter(Tracker.bill_reminder_id == rid).update({"bill_reminder_id": None}, synchronize_session=False)
    session.delete(r)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- .ics feed

def _esc(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line):
    """Fold at 75 octets (RFC 5545); a continuation line starts with a space that counts towards its 75."""
    lines, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            lines.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    lines.append(cur)
    return "\r\n".join(lines)


def _inr(amount):
    n = int(round(amount))
    s = str(abs(n))
    if len(s) > 3:
        head, tail, groups = s[:-3], s[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups + [tail])
    return "₹" + ("-" if n < 0 else "") + s


def _monthday(day):
    """BYMONTHDAY rule. Days past the 28th pick the last of 28..day that exists, i.e. clamp to the month's last day."""
    if day <= 28:
        return f"BYMONTHDAY={day}"
    return "BYMONTHDAY=" + ",".join(str(d) for d in range(28, day + 1)) + ";BYSETPOS=-1"


def _rrule(repeat, day, month):
    if repeat == "quarterly":
        return f"FREQ=MONTHLY;INTERVAL=3;{_monthday(day)}"
    if repeat == "yearly":
        return f"FREQ=YEARLY;BYMONTH={month};{_monthday(day)}"
    return f"FREQ=MONTHLY;{_monthday(day)}"


def _first_on_or_after(floor, repeat, day, month):
    for i in range(37):
        y, m = _shift_month(floor.year, floor.month, i)
        if (repeat == "quarterly" and (m - month) % 3) or (repeat == "yearly" and m != month):
            continue
        d = _clamped(y, m, day)
        if d >= floor:
            return d
    return floor


def _vevent(uid, stamp, summary, start, rrule, description="", category="", recurrence_id=None):
    """One VEVENT. With `recurrence_id` it is a moved instance of the series `uid`, with no RRULE of its own."""
    lines = ["BEGIN:VEVENT", f"UID:{uid}@spendlens", f"DTSTAMP:{stamp}"]
    if recurrence_id is not None:
        lines.append(f"RECURRENCE-ID;VALUE=DATE:{recurrence_id:%Y%m%d}")
    lines.append(f"DTSTART;VALUE=DATE:{start:%Y%m%d}")
    if rrule:
        lines.append(f"RRULE:{rrule}")
    lines.append(f"SUMMARY:{_esc(summary)}")
    if description:
        lines.append(f"DESCRIPTION:{_esc(description)}")
    if category:
        lines.append(f"CATEGORIES:{_esc(category)}")
    lines += ["TRANSP:TRANSPARENT", "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(summary)}", "TRIGGER:PT9H", "END:VALARM", "END:VEVENT"]
    return lines


def _titled(name, amount):
    return f"{name} {_inr(amount)}" if amount else name


@router.get("/calendar.ics")
def reminder_feed(types: str = Query(None), today: str = Query(None), session=Depends(get_session)):
    ref = _parse_today(today)
    all_cats = session.query(ReminderCategory).filter(ReminderCategory.user_id == USER_ID).order_by(ReminderCategory.sort_order, ReminderCategory.id).all()
    if types is None:
        chosen, want_log, want_vacations = {c.id for c in all_cats}, True, True
    else:
        tokens = {t.strip() for t in types.split(",") if t.strip()}
        chosen = {c.id for c in all_cats if str(c.id) in tokens}
        want_log, want_vacations = "log" in tokens, "vacation" in tokens
    names = {c.id: c.name for c in all_cats}
    kinds = {c.kind: c.id for c in all_cats if c.kind}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    year_start = date(ref.year, 1, 1)

    overrides = {}
    for o in session.query(ReminderOverride).order_by(ReminderOverride.month):
        overrides.setdefault(o.reminder_id, []).append(o)
    body = []
    for r in session.query(Reminder).filter(Reminder.user_id == USER_ID, Reminder.enabled.is_(True)).order_by(Reminder.id):
        if r.category_id not in chosen:
            continue
        try:
            floor = datetime.strptime(r.created_at[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            floor = year_start
        start = _first_on_or_after(floor, r.repeat, r.day, r.month)
        summary = _titled(r.name, r.amount)
        body += _vevent(f"reminder-{r.id}", stamp, summary, start, _rrule(r.repeat, r.day, r.month), r.note, names[r.category_id])
        for o in overrides.get(r.id, []):
            oy, om = int(o.month[:4]), int(o.month[5:7])
            original = _clamped(oy, om, r.day)
            if not _falls_in(r, om) or original < start:
                continue  # not an instance of the series, so a RECURRENCE-ID would point at nothing
            body += _vevent(f"reminder-{r.id}", stamp, summary, _clamped(oy, om, o.day), None, r.note, names[r.category_id],
                            recurrence_id=original)

    auto = []
    if kinds.get("card") in chosen:
        auto += [(kinds["card"], i) for i in _card_items(_active_cards(session), ref.year, ref.month)]
    if kinds.get("sip") in chosen:
        auto += [(kinds["sip"], i) for i in _sip_items(session)]
    for cid, i in auto:
        body += _vevent(i["uid"], stamp, _titled(i["name"], i["amount"]), _first_on_or_after(year_start, "monthly", i["day"], None),
                        _rrule("monthly", i["day"], None), i["note"], names[cid])

    if want_vacations:
        for v in session.query(Vacation).filter(Vacation.user_id == USER_ID).order_by(Vacation.start_date, Vacation.id):
            start, end = date.fromisoformat(v.start_date), date.fromisoformat(v.end_date)
            body += ["BEGIN:VEVENT", f"UID:vacation-{v.id}@spendlens", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                     f"DTEND;VALUE=DATE:{end + timedelta(days=1):%Y%m%d}", f"SUMMARY:{_esc(v.name)}", "TRANSP:TRANSPARENT", "END:VEVENT"]

    settings = _settings_view(session.get(ReminderSettings, USER_ID))
    if want_log and settings["nudge_on"]:
        hh, mm = settings["nudge_time"].split(":")
        body += ["BEGIN:VEVENT", "UID:log-nudge@spendlens", f"DTSTAMP:{stamp}", f"DTSTART:{ref:%Y%m%d}T{hh}{mm}00", "DURATION:PT15M",
                 "RRULE:FREQ=DAILY", "SUMMARY:Log today's expenses", "DESCRIPTION:Open SpendLens and fill in today's expenses.",
                 "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Log today's expenses", "TRIGGER:PT0S", "END:VALARM", "END:VEVENT"]

    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SpendLens//Reminders//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            "X-WR-CALNAME:SpendLens", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    text = "\r\n".join(_fold(line) for line in head + body + ["END:VCALENDAR"]) + "\r\n"
    return Response(content=text.encode("utf-8"), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'inline; filename="spendlens-reminders.ics"', "Cache-Control": "no-cache"})
