"""When to pay a credit-card bill.

The idea
--------
A card lends you the money from the day you spend until the bill's **due date**, free.
That is the *float*. Paying the bill the day it is generated, or paying as you go, hands
the float back: the money sits in the card issuer's pocket instead of earning something in
yours. Paying after the due date is far worse - a late fee, plus interest charged on every
rupee of the cycle from the day it was spent, at roughly 45% a year.

So the best day to pay is the due date, with a small safety margin. The two risks are not
symmetric, which is why the margin exists:

    one day early costs   amount x rate / 365            (a few rupees)
    one day late costs    a late fee + ~45% a year on the whole cycle   (hundreds)

What this module does
---------------------
- `statement_on_or_after`, `due_date`, `pay_on`: the calendar. A cycle is a statement day
  each month plus a number of days to the due date. The pay date steps back off a weekend
  because a payment made on a Saturday or Sunday may not be credited until Monday.
- `pair_payments`: matches what you paid against what you spent, oldest first, so every
  rupee of payment is tied to the spend it settled.
- `habit`: from those pairs, how early you actually pay and what that has cost in float.
- `upcoming`: the next statement, due and pay dates, and what paying on the bill's arrival
  instead would give away.

Everything here is a pure function of dates and amounts, so it can be tested without a
database. The money value of float is only as good as the rate you put on it: it is what
the money would otherwise earn (a savings account, a liquid fund), not what the card charges.
"""
import calendar
from collections import defaultdict, deque
from datetime import date, timedelta

EPS = 0.005


def _clamp(y, m, day):
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def _next_month(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def statement_on_or_after(d, sday):
    """The first statement date on or after `d`. A spend on the statement day is on that bill."""
    c = _clamp(d.year, d.month, sday)
    if d <= c:
        return c
    return _clamp(*_next_month(d.year, d.month), sday)


def due_date(stmt, grace):
    return stmt + timedelta(days=grace)


def pay_on(due, buffer):
    """The date to pay: `buffer` days before the due date, and never on a weekend."""
    d = due - timedelta(days=max(buffer, 0))
    while d.weekday() >= 5:  # Saturday or Sunday: pay the Friday before
        d -= timedelta(days=1)
    return d


def pair_payments(charges, credits):
    """Match credits to the charges they settled, oldest charge first.

    charges: [(date, amount)] or [(date, amount, statement_date)]; the statement date, when the
    statement prints one, beats working it out from the date, because a bank books a spend a
    day or two late and it can land on the next bill. credits: [(date, amount, free)] where
    `free` marks a credit that did not come out of your pocket (a refund, a cashback), so it has
    no float cost. Returns (pairs, outstanding) with pairs
    [(charge_date, credit_date, amount, free, statement_date or None)].

    A payment made before there is anything to settle waits in a pool and is matched to the
    next charge: that is a genuine pre-payment and it keeps its own (early) date. Credits
    dated before the first charge are dropped, because they settle a balance from before the
    data begins and would otherwise be mistaken for pre-payments.
    """
    if not charges:
        return [], 0.0
    charges = [(c + (None,))[:3] for c in charges]  # normalise to (date, amount, statement)
    first = min(c[0] for c in charges)
    events = sorted([(d, 0, a, st) for d, a, st in charges] + [(d, 1, a, f) for d, a, f in credits],
                    key=lambda e: (e[0], e[1]))  # on one day, charges come before credits
    unpaid, pool, pairs = deque(), deque(), []
    for d, kind, amt, free in events:
        rem = amt
        if kind == 0:  # a charge: take from waiting pre-payments first
            while rem > EPS and pool:
                pd, pamt, pfree = pool[0]
                take = min(rem, pamt)
                pairs.append((d, pd, take, pfree, free))  # for a charge, `free` holds its statement
                rem -= take
                if pamt - take < EPS:
                    pool.popleft()
                else:
                    pool[0] = (pd, pamt - take, pfree)
            if rem > EPS:
                unpaid.append([d, rem, free])
        else:  # a credit: settle the oldest unpaid charges
            if d < first:
                continue
            while rem > EPS and unpaid:
                cd, camt, cst = unpaid[0]
                take = min(rem, camt)
                pairs.append((cd, d, take, free, cst))
                rem -= take
                if camt - take < EPS:
                    unpaid.popleft()
                else:
                    unpaid[0][1] = camt - take
            if rem > EPS:
                pool.append((d, rem, free))
    return pairs, round(sum(u[1] for u in unpaid), 2)


def habit(pairs, sday, grace, buffer, rate, cycles=6):
    """How you actually pay, against paying on the best day.

    rate is the yearly % the money would earn instead. Only payments out of your own pocket
    count towards cost; refunds and cashback are credits you did nothing to time.
    """
    paid = forgone = late_amt = early_w = used_w = avail_w = in_window = 0.0
    by_cycle = defaultdict(lambda: {"billed": 0.0, "paid": 0.0, "forgone": 0.0, "early_w": 0.0, "late": 0.0})
    first = last = None
    for cd, pd, amt, free, billed_on in pairs:
        stmt = billed_on or statement_on_or_after(cd, sday)
        due = due_date(stmt, grace)
        best = pay_on(due, buffer)
        c = by_cycle[stmt]
        c["billed"] += amt
        first = cd if first is None or cd < first else first
        last = cd if last is None or cd > last else last
        if free:
            continue
        early = (best - pd).days
        cost = amt * max(early, 0) * rate / 36500
        paid += amt
        forgone += cost
        early_w += amt * early
        used_w += amt * max((pd - cd).days, 0)
        avail_w += amt * (due - cd).days
        if pd > due:
            late_amt += amt
            c["late"] += amt
        if best - timedelta(days=2) <= pd <= due:
            in_window += amt
        c["paid"] += amt
        c["forgone"] += cost
        c["early_w"] += amt * early
    span = max(((last - first).days if first else 0), 30)
    rows = []
    for stmt in sorted(by_cycle, reverse=True)[:cycles]:
        c = by_cycle[stmt]
        due = due_date(stmt, grace)
        rows.append({"statement": stmt.isoformat(), "due": due.isoformat(), "pay_on": pay_on(due, buffer).isoformat(),
                     "billed": round(c["billed"], 2), "paid": round(c["paid"], 2),
                     "early_days": round(c["early_w"] / c["paid"], 1) if c["paid"] else None,
                     "forgone": round(c["forgone"], 2), "late": round(c["late"], 2)})
    w = (lambda x: round(x / paid, 1)) if paid else (lambda x: 0.0)
    return {
        "paid": round(paid, 2),
        "days_credit_used": w(used_w),          # average days between spending and paying
        "days_credit_available": w(avail_w),    # average days between spending and the due date
        "days_early": w(early_w),               # average days before the best day that you paid
        "forgone": round(forgone, 2),           # float given away over the whole history
        "forgone_per_year": round(forgone * 365 / span, 2),
        "late_amount": round(late_amt, 2),
        "on_time_pct": round(in_window / paid * 100, 1) if paid else 0.0,
        "span_days": span,
        "cycles": rows,
    }


def upcoming(today, sday, grace, buffer, rate, expected=0.0, n=3):
    """The next statements with their due and pay dates.

    `expected` is a typical bill. It is used for one thing: what paying the day the bill
    arrives, rather than on the pay date, would give away.
    """
    out, s = [], statement_on_or_after(today, sday)
    for _ in range(n):
        due = due_date(s, grace)
        pay = pay_on(due, buffer)
        gap = max((pay - (s + timedelta(days=1))).days, 0)  # the bill is available the day after
        out.append({"statement": s.isoformat(), "due": due.isoformat(), "pay_on": pay.isoformat(),
                    "days_to_pay": (pay - today).days, "days_kept": gap,
                    "kept_value": round(expected * gap * rate / 36500, 2)})
        s = _clamp(*_next_month(s.year, s.month), sday)
    return out


def previous(today, sday, grace, buffer):
    """The most recent statement that has already been issued, with its dates."""
    nxt = statement_on_or_after(today, sday)
    y, m = (nxt.year - 1, 12) if nxt.month == 1 else (nxt.year, nxt.month - 1)
    s = _clamp(y, m, sday)
    if s >= today:  # today is the statement day: that one is just arriving, step back once more
        y, m = (s.year - 1, 12) if s.month == 1 else (s.year, s.month - 1)
        s = _clamp(y, m, sday)
    due = due_date(s, grace)
    return {"statement": s.isoformat(), "due": due.isoformat(), "pay_on": pay_on(due, buffer).isoformat(),
            "days_to_pay": (pay_on(due, buffer) - today).days}
