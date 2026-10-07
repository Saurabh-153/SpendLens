"""Parser for Bank of Baroda (BOBCARD) credit-card statements, built against the BOB Eterna RuPay card.

A monthly statement prints what the SBI one does, in its own way: a statement date and due date,
an "at a glance" block (opening balance, payments, new purchases, closing balance) and a
reward-points summary (opening, earned, redeemed, closing). So this parser can be held to the same
standard as SBI's: **the transactions must add up to the statement's own totals**, and the cycle
(statement day, days to the due date) is read, not assumed. Reward points are printed per
transaction as well as in total, so rewards are *read*, not estimated.

Two layouts of the same statement exist, from two PDF generators:

- the monthly layout, whose text extracts one field per line (Hindi and English labels), and
- a table layout whose default extraction is one *character* per line, but whose layout-aware
  extraction (`pypdf` `extraction_mode="layout"`) gives clean columns. `cards.read_pdf` falls back to
  it when the default text is unreadable.

Both are flattened into the same stream of fields, so one record parser reads either.

A transaction is
    date, [ref], particulars (may wrap), [country code 356], [reward points], currency, source amount, amount, DR|CR
UPI-linked spends (`UPI-MERCHANT`) carry no country code, so a lone number after them is the points; a
card spend carries the country code first (356 is India), then the points. A code other than 356 marks
an international spend.
"""
import re
from datetime import datetime

DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MONEY = re.compile(r"^[\d,]+\.\d{2}$")
AMT_DC = re.compile(r"^([\d,]+\.\d{2})\s*(DR|CR)$")
REF = re.compile(r"^(?=[A-Z0-9]*\d)[A-Z0-9]{5,8}$")
# The card number is masked two ways: 356162XXXXXX1395 and XXXXXX********1395.
CARD_NO = re.compile(r"(?:\d{6}|X{6})[X*]{6,8}(\d{4})")
INDIA = "356"
PERIOD = re.compile(r"(\d{1,2} [A-Z][a-z]{2}, \d{4})\s+(?:to|To)\s+(\d{1,2} [A-Z][a-z]{2}, \d{4})")
NOISE_PREFIXES = ("Page ", "Please register", "For Queries")
NOISE_WORDS = {"Date", "Ref. No.", "Particulars", "Reward", "Points", "Source", "Currency", "Source Amt.", "Amount",
               "Transaction Details", "|", "of", "Page"}


def detect(text):
    """BOBCARD statements name the issuer and carry the `Statement Period` as `26 Aug, 2026 to 25 Sep, 2026`."""
    low = text.lower()
    return ("bobcard" in low or "bob-rupay" in low) and bool(PERIOD.search(text))


def _money(s):
    return float(s.replace(",", ""))


def _iso(d):
    return datetime.strptime(d, "%d/%m/%Y").date().isoformat()


def _long_date(s):
    return datetime.strptime(s.replace(",", ""), "%d %b %Y").date().isoformat()


def _fields(text):
    """Flatten either text form into a stream of fields, with 'amount DR' split into two."""
    out = []
    for line in text.splitlines():
        for part in re.split(r"\s{2,}|\t", line.strip()):
            part = part.strip()
            if not part:
                continue
            m = AMT_DC.match(part)
            if m:
                out.extend([m.group(1), m.group(2)])
            else:
                out.append(part)
    return out


def _noise(f):
    """Page furniture that can fall in the middle of a record: labels, Hindi labels, footers."""
    return f in NOISE_WORDS or not f.isascii() or len(f) > 90 or f.startswith(NOISE_PREFIXES)


def _records(fields):
    """Group fields into records: from a date field to the DR/CR that closes it, as (start index, fields).
    Page footers (`Page`, n, `of`, m) fall between records and sometimes inside one; they are dropped."""
    recs, cur, start, i = [], None, 0, 0
    while i < len(fields):
        f = fields[i]
        if f == "Page":                       # Page n of m: skip the three numbers that follow
            i += 4
            continue
        if DATE.match(f) and i + 1 < len(fields) and not DATE.match(fields[i + 1]):
            cur, start = [f], i          # a transaction never contains a second date: a new date starts afresh
        elif cur is None:
            pass
        elif f in ("DR", "CR"):
            cur.append(f)
            recs.append((start, cur))
            cur = None
        elif not _noise(f):
            cur.append(f)
        i += 1
    return recs


def _parse_record(rec):
    """One transaction, or None for something that only looks like one (the due-date line in the header,
    `14/10/2026 Pay Now 200.00 377.61 DR`, has no currency). A real line that is skipped by mistake
    is caught by the statement's own totals, so skipping is safe."""
    date, dc, amt = rec[0], rec[-1], rec[-2]
    body = rec[1:-2]                                  # between the date and the two amounts
    if len(body) < 2 or not MONEY.match(amt) or not MONEY.match(body[-1]):
        return None
    body = body[:-1]                                  # drop the source amount
    if not (body and re.fullmatch(r"[A-Z]{3}", body[-1])):
        return None
    ccy = body.pop()
    ref = body.pop(0) if body and REF.match(body[0]) and not body[0].isdigit() else ""
    ints = []
    while body and re.fullmatch(r"\d{1,6}", body[-1]):
        ints.insert(0, body.pop())
    # The monthly layout prints a merchant as "UPI-THE_RASAGANGA_VEG_" and the table layout renders the
    # underscores as spaces. Normalising them lets the same statement in either layout de-duplicate.
    particulars = re.sub(r"[_\s]+", " ", " ".join(body)).strip()
    if not particulars:
        return None
    upi = particulars.upper().startswith("UPI-")
    country, points = ("", ints[0] if ints else "") if upi else ((ints[0] if ints else ""), (ints[1] if len(ints) > 1 else ""))
    return {"tx_date": _iso(date), "ref": ref, "detail": particulars, "amount": _money(amt),
            "dc": dc[0], "ccy": "" if ccy == "INR" else ccy,
            "points": int(points) if points else 0,
            "intl": int(bool(country) and country != INDIA)}


def _kind(r):
    u = r["detail"].upper()
    if r["dc"] == "C":
        if "CASHBACK" in u or "WAIVER" in u:         # a fuel-surcharge waiver is a benefit, not a refund of spend
            return "cashback"
        if any(k in u for k in ("PAYMENT", "BBPS", "NEFT", "IMPS", "RAZORPAY", "CRED", "BILLDESK", "UPI")):
            return "payment"
        return "refund"
    if any(u.startswith(k) for k in ("GST", "IGST", "CGST", "SGST", "FEE", "FINANCE CHARGE", "INTEREST", "LATE", "ANNUAL",
                                      "MEMBERSHIP", "PROCESSING", "CASH ADVANCE FEE")):
        return "fee"
    return "spend"


def _header_numbers(head):
    """The statement's own figures, found by what they must satisfy rather than where they sit.

    The two layouts order their header differently, so positions cannot be trusted. But
    opening - payments + purchases = closing, and opening + earned - redeemed = closing for points,
    which no accidental run of numbers will satisfy.
    """
    # a balance followed by CR is a credit balance (the bank owes you): negative. A small one can print
    # with no leading digit ("-.21"), so the figure is allowed to start at the decimal point.
    vals = [(-1 if i + 1 < len(head) and head[i + 1] == "CR" else 1) * _money(m.group(1))
            for i, f in enumerate(head) for m in [re.search(r"(-?[\d,]*\.\d{2})", f)] if m]
    glance = None
    for k in range(len(vals) - 3):
        o, p, n, c = vals[k:k + 4]
        if abs(o - p + n - c) < 0.015 and (p or n or o):
            glance = (o, p, n, c)
            break
    if not glance:      # a zero opening balance is printed as a bare 0, leaving three numbers: payments, purchases, closing
        for k in range(len(vals) - 2):
            p, n, c = vals[k:k + 3]
            # the opening balance can be a few paise of credit left from last month and is then not
            # printed as a number, so the three figures may miss by under a rupee
            if abs(n - p - c) < 1.0 and n > 0:
                glance = (round(c + p - n, 2), p, n, c)
                break
    ints = [int(f) for f in head if re.fullmatch(r"\d{1,7}", f)]
    points = None
    for k in range(len(ints) - 3):
        o, e, r, c = ints[k:k + 4]
        if o + e - r == c and (e or o):
            points = (o, e, r, c)
            break
    dates = [f for f in head if DATE.match(f)]
    # the sanctioned limit is the largest rupee figure; it can print without decimals ("200,000")
    limits = [float(m.group(1).replace(",", "")) for f in head for m in [re.match(r"^(?:₹\s*)?(\d{1,3}(?:,\d{2,3})+(?:\.\d{2})?)$", f)] if m]
    return glance, points, dates, (max(limits) if limits else 0.0)


def parse(text):
    """Parse one BOB statement. Returns a list with one entry (the common shape), or raises ValueError."""
    pm = PERIOD.search(text)
    if not pm:
        raise ValueError("no statement period found - is this a BOBCARD statement?")
    fields = _fields(text)
    parsed = [(i, _parse_record(r)) for i, r in _records(fields)]
    parsed = [(i, r) for i, r in parsed if r]
    if not parsed:
        raise ValueError("no transactions found")
    rows = [r for _, r in parsed]
    glance, points, dates, limit = _header_numbers(fields[:parsed[0][0]])
    if not glance:
        raise ValueError("the statement's opening, payments, purchases and closing balance did not parse")
    if len(dates) < 2:
        raise ValueError("no statement date and due date found")
    for r in rows:
        r["kind"] = _kind(r)
        r["merchant"] = re.sub(r"^UPI-", "", r["detail"])
        r["city"], r["emi"] = "", 0
        r["is_spend"] = int(r["dc"] == "D" and r["kind"] == "spend")

    opening, payments, purchases, closing = glance
    debits = round(sum(r["amount"] for r in rows if r["dc"] == "D"), 2)
    credits = round(sum(r["amount"] for r in rows if r["dc"] == "C"), 2)
    # The check that makes this import trustworthy: the lines must add up to the statement's own figures.
    if abs(debits - purchases) > 1 or abs(credits - payments) > 1:
        raise ValueError(f"transactions add up to debits {debits:,.2f} / credits {credits:,.2f} but the statement says "
                         f"{purchases:,.2f} / {payments:,.2f} - refusing to import a partial statement")
    # Reward points are printed per line and as a total. The total can exceed the lines (bonus and adjustment
    # points belong to no line), so the lines are not required to add up to it. But the lines can never exceed
    # it: the same February statement in its table layout shows 152 points on a purchase the monthly layout
    # shows as 76, putting its lines at 1,107 against a printed total of 1,040. When a statement contradicts
    # its own total the per-line points are unreliable, so they are dropped and the printed total is kept.
    # The money check above stays exact.
    if points and sum(r["points"] for r in rows) > points[1]:
        for r in rows:
            r["points"] = 0

    card_no = CARD_NO.search(text)
    stmt, due = _iso(dates[0]), _iso(dates[1])
    spend_total = round(sum(r["amount"] for r in rows if r["is_spend"]), 2)
    return [{
        "card": {"issuer": "Bank of Baroda", "last4": card_no.group(1) if card_no else "", "name": "BOB Eterna",
                 "profile": "bob_eterna"},
        "kind": "cycle", "validation": "total",
        "period_from": _long_date(pm.group(1)), "period_to": _long_date(pm.group(2)),
        "stmt_date": stmt, "due_date": due,
        "total_due": closing if closing > 0 else 0.0, "min_due": 0.0,
        "credit_limit": limit, "cash_limit": 0.0, "available_credit": 0.0,
        "credits": credits, "purchases": spend_total, "fees": round(sum(r["amount"] for r in rows if r["kind"] == "fee"), 2),
        "cashback_reported": None, "points_earned": points[1] if points else None,
        "points_balance": points[3] if points else None,
        "txns": [{k: r[k] for k in ("tx_date", "detail", "merchant", "city", "amount", "dc", "emi", "is_spend", "kind",
                                    "ref", "ccy", "points")} for r in rows],
    }]
