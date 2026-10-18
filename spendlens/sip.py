"""Monthly SIPs: on each holding's SIP day the amount is added to its invested and present value.

One way only: a SIP is added on top of whatever the holding is worth at that moment, and later
manual edits are never recalculated or reverted. Each application is logged in `sip_log`, and
`holdings.sip_applied` (YYYY-MM) records the last month applied so a month is never applied twice.
Months that were missed (app not opened) are caught up the next time the data is read.
"""
import calendar
from datetime import date, datetime, timezone

from db import failover
from db.models import Holding
from db.models.portfolio import LedgerTransaction, SipLog

DIRECT = ("MF", "FD", "PF")


def _ym(d):
    return f"{d.year:04d}-{d.month:02d}"


def _next(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def _prev(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y - (m == 1):04d}-{(m - 2) % 12 + 1:02d}"


def _due_date(ym, day):
    y, m = int(ym[:4]), int(ym[5:])
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def baseline(day, today):
    """First SIP month to apply: this month only if its date is still ahead, else next month's."""
    cur = _ym(today)
    return _prev(cur) if _due_date(cur, day) > today else cur


def set_sip(session, hid, amount, day, today=None):
    """Set a holding's SIP. Does not commit: the caller does, together with its own changes."""
    today = today or date.today()
    h = session.get(Holding, hid)
    if not h:
        return False
    applied = h.sip_applied
    if day > 0 and (h.sip_day != day or not applied):
        applied = baseline(day, today)
    h.sip_amount, h.sip_day, h.sip_applied = amount, day, applied or ""
    return True


def _now_utc_text():
    """The timestamp format SQLite's datetime('now') produced for sip_log.applied_at (UTC, to the second)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def apply_due_sips(session, today=None):
    """Apply every SIP whose date has passed and was not applied yet. Returns the number applied."""
    if failover.read_only():  # on the read-only mirror: catch up once PostgreSQL is back
        return 0
    today = today or date.today()
    cur, n = _ym(today), 0
    for h in session.query(Holding).filter(Holding.sip_amount > 0, Holding.sip_day > 0).order_by(Holding.id).all():
        applied = h.sip_applied or baseline(h.sip_day, today)
        qty, buy, cmp_ = h.qty, h.buy_price, h.cmp
        units = 0.0
        m = _next(applied)
        while m <= cur and _due_date(m, h.sip_day) <= today:
            amt = h.sip_amount
            if h.asset_type == "MF" and (h.units or 0) > 0 and (h.nav or 0) > 0:
                units = (units or h.units) + amt / h.nav  # priced by NAV: buy units at today's NAV
                qty, buy, cmp_ = 1.0, buy + amt, units * h.nav
            elif h.asset_type in DIRECT:
                qty, buy, cmp_ = 1.0, buy + amt, cmp_ + amt
            elif cmp_ > 0:
                units = amt / cmp_
                buy = (qty * buy + amt) / (qty + units)
                qty += units
            else:
                break  # priced holding without a price: nothing sensible to add
            due = _due_date(m, h.sip_day).isoformat()
            session.add(SipLog(holding_id=h.id, holding_name=h.name, month=m, sip_date=due, amount=amt, applied_at=_now_utc_text()))
            unit_priced = h.asset_type not in DIRECT or (h.asset_type == "MF" and (h.units or 0) > 0)
            nav = (h.nav if h.asset_type == "MF" else cmp_) if unit_priced else 0
            session.add(LedgerTransaction(holding_id=h.id, name=h.name, tx_date=due, kind="BUY", qty=amt / nav if nav else 0,
                                          price=nav or 0, amount=amt, source="sip", applied=1))
            applied, n = m, n + 1
            m = _next(m)
        # written back even when nothing was due, as before (it also stores the baseline month on first sight)
        h.qty, h.buy_price, h.cmp, h.sip_applied, h.units = qty, buy, cmp_, applied, units or h.units
    if n:
        session.commit()
    return n
