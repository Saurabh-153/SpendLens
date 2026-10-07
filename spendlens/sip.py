"""Monthly SIPs: on each holding's SIP day the amount is added to its invested and present value.

One way only: a SIP is added on top of whatever the holding is worth at that moment, and later
manual edits are never recalculated or reverted. Each application is logged in `sip_log`, and
`holdings.sip_applied` (YYYY-MM) records the last month applied so a month is never applied twice.
Months that were missed (app not opened) are caught up the next time the data is read.
"""
import calendar
from datetime import date

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


def set_sip(db, hid, amount, day, today=None):
    today = today or date.today()
    row = db.execute("SELECT sip_day, sip_applied FROM holdings WHERE id=?", (hid,)).fetchone()
    if not row:
        return False
    applied = row["sip_applied"]
    if day > 0 and (row["sip_day"] != day or not applied):
        applied = baseline(day, today)
    db.execute("UPDATE holdings SET sip_amount=?, sip_day=?, sip_applied=? WHERE id=?", (amount, day, applied or "", hid))
    return True


def apply_due_sips(db, today=None):
    """Apply every SIP whose date has passed and was not applied yet. Returns the number applied."""
    today = today or date.today()
    cur, n = _ym(today), 0
    import ledger
    ledger.ensure(db)
    rows = db.execute("SELECT * FROM holdings WHERE sip_amount>0 AND sip_day>0").fetchall()
    for h in rows:
        applied = h["sip_applied"] or baseline(h["sip_day"], today)
        qty, buy, cmp_ = h["qty"], h["buy_price"], h["cmp"]
        units = 0.0
        m = _next(applied)
        while m <= cur and _due_date(m, h["sip_day"]) <= today:
            amt = h["sip_amount"]
            if h["asset_type"] == "MF" and (h["units"] or 0) > 0 and (h["nav"] or 0) > 0:
                units = (units or h["units"]) + amt / h["nav"]  # priced by NAV: buy units at today's NAV
                qty, buy, cmp_ = 1.0, buy + amt, units * h["nav"]
            elif h["asset_type"] in DIRECT:
                qty, buy, cmp_ = 1.0, buy + amt, cmp_ + amt
            elif cmp_ > 0:
                units = amt / cmp_
                buy = (qty * buy + amt) / (qty + units)
                qty += units
            else:
                break  # priced holding without a price: nothing sensible to add
            db.execute("INSERT INTO sip_log (holding_id, holding_name, month, sip_date, amount) VALUES (?,?,?,?,?)",
                       (h["id"], h["name"], m, _due_date(m, h["sip_day"]).isoformat(), amt))
            unit_priced = h["asset_type"] not in DIRECT or (h["asset_type"] == "MF" and (h["units"] or 0) > 0)
            nav = (h["nav"] if h["asset_type"] == "MF" else cmp_) if unit_priced else 0
            db.execute("""INSERT INTO transactions (holding_id, name, tx_date, kind, qty, price, amount, source, applied)
                          VALUES (?,?,?,'BUY',?,?,?,'sip',1)""",
                       (h["id"], h["name"], _due_date(m, h["sip_day"]).isoformat(), amt / nav if nav else 0, nav or 0, amt))
            applied, n = m, n + 1
            m = _next(m)
        db.execute("UPDATE holdings SET qty=?, buy_price=?, cmp=?, sip_applied=?, units=? WHERE id=?",
                   (qty, buy, cmp_, applied, units or h["units"], h["id"]))
    if n:
        db.commit()
    return n
