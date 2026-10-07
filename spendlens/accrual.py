"""Auto-valuation of fixed-return holdings (FD, RD, PF ...) from rate, opening date and closing date.

Present value = opening principal grown at the rate from the opening date + every applied SIP grown
from its own date, up to today (frozen at the closing date). Computed on read, never stored, so
changing the rate or dates takes effect immediately. Compounding: Q quarterly, A annual, S simple.
"""
import calendar
import re
from datetime import date


def _iso(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _grow(amount, rate_pct, frm, to, mode):
    t = max((to - frm).days, 0) / 365
    r = rate_pct / 100
    if mode == "S":
        return amount * (1 + r * t)
    n = 1 if mode == "A" else 4
    return amount * (1 + r / n) ** (n * t)


def is_auto(h):
    return not h.get("manual") and (h.get("rate") or 0) > 0 and _iso(h.get("start_date")) is not None


def _years_on(d, n=1):
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + n, day=28)


def parse_credits(text):
    """'2024-05-31, 13759' per line -> sorted [(date, amount)]; bad lines are ignored."""
    out = []
    for line in re.split(r"[;\n]", text or ""):
        parts = line.replace(",", " ").split()
        if len(parts) >= 2 and _iso(parts[0]):
            try:
                out.append((_iso(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return sorted(out)


def _credited(h, principal, start, end, asof):
    """Cumulative FD: interest is credited once a year, so the value is principal + credits so far.

    Known credits (entered from the bank) are used as they are; later anniversaries are projected at
    the rate compounded quarterly on the running balance. At maturity the last part-year is added.
    """
    r = h["rate"] / 100
    credits = [(d, a) for d, a in parse_credits(h.get("credits")) if d <= asof]
    bal = principal + sum(a for _, a in credits)
    last = credits[-1][0] if credits else start
    nxt = _years_on(last)
    while nxt <= asof and not (end and nxt >= end):
        bal *= (1 + r / 4) ** 4
        last, nxt = nxt, _years_on(nxt)
    if end and asof >= end:
        bal = _grow(bal, h["rate"], last, end, "Q")
    return bal


def _deposits(start, day, last, strictly_before):
    """Dates of a recurring deposit: the opening date, then `day` of every following month."""
    out, y, m = [start], start.year, start.month
    while True:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        d = date(y, m, min(day or start.day, calendar.monthrange(y, m)[1]))
        if (d >= last) if strictly_before else (d > last):
            return out
        out.append(d)


def auto_value(h, sips, today=None):
    """(present, invested) for an auto-valued holding, or None.

    h: holding dict; sips: [(iso_date, amount)] SIPs the app applied to it.
    Recurring deposit (h['rd']): one deposit of the SIP amount per month from the opening date, each
    earning interest from its own date; invested is the sum of the deposits.
    """
    if not is_auto(h):
        return None
    today = today or date.today()
    start, end = _iso(h["start_date"]), _iso(h.get("maturity"))
    asof = min(today, end) if end else today
    mode = h.get("compounding") or "Q"
    if h.get("rd") and (h.get("sip_amount") or 0) > 0:
        if asof < start:
            return 0.0, 0.0
        deps = _deposits(start, h.get("sip_day") or 0, asof, bool(end and end <= today))
        amt = h["sip_amount"]
        return sum(_grow(amt, h["rate"], d, asof, mode) for d in deps), amt * len(deps)
    invested = h["qty"] * h["buy_price"]
    if mode == "Y":
        return _credited(h, invested, start, end, asof), invested
    sips = [(d, a) for d, a in sips if _iso(d) and _iso(d) >= start]
    opening = invested - sum(a for _, a in sips)
    total = _grow(opening, h["rate"], start, max(asof, start), mode)
    for d, a in sips:
        total += _grow(a, h["rate"], _iso(d), max(asof, _iso(d)), mode)
    return total, invested
