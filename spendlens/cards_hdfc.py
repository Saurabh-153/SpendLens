"""Parser for HDFC Bank credit-card statements, built against the Tata Neu Infinity HDFC Bank card.

HDFC prints what SBI and BOB do: statement and billing period, a due date, a summary line (previous
dues, payments/credits received, purchases/debits, finance charges), the credit limit, and a rewards
summary (here NeuCoins: opening, earned, transferred to Tata Neu, adjusted/lapsed). So the import is
held to the same strict standard: **the transaction lines must add up to the printed totals**, and the
billing cycle is read from the printed dates, not assumed. Rewards are printed per transaction (base
NeuCoins) and in total, so they are read, not estimated.

How the text looks
------------------
`pypdf` returns readable text, but in blocks that are out of order (the transaction block can land
between header blocks), and the rupee sign comes out as the letter `C`. A transaction is

    02/08/2026| 19:02 EMI TATA DIGITAL PRIVATE + 45  C 3,000.00 l          a debit, 45 base NeuCoins
    03/08/2026| 07:58 BPPY CC PAYMENT BD016215075830JG7ii (Ref#
    ST262160083000010393711) +  C 3,432.00 l                               a credit (a payment), wrapped

A `+` straight before the `C` marks a **credit**; a `+` followed by a number is the base NeuCoins
earned on that line, so the two are told apart by what follows the plus. The trailing letter is a
spend-category icon. Because the sign convention is an inference, the printed totals are the proof: the
credits must equal "payments/credits received" and the debits "purchases/debit" plus finance charges.

The total due is rounded down to the rupee (3,957.35 is printed as 3,957.00); the paise carry to the
next statement as part of "previous statement dues".
"""
import re
from datetime import datetime

DATE_TIME = re.compile(r"^(\d{2}/\d{2}/\d{4})\|\s*(\d{2}:\d{2})\s+(.*)$")
AMOUNT = re.compile(r"C\s?([\d,]+\.\d{2})")
# description, optional "+ N" base NeuCoins, optional credit "+", the amount, a trailing category icon
LINE_TAIL = re.compile(r"^(?P<desc>.*?)\s*(?:\+\s*(?P<coins>\d+))?\s*(?P<credit>\+)?\s+C\s?(?P<amt>[\d,]+\.\d{2})\s*\S?\s*$")
PERIOD = re.compile(r"(\d{2} [A-Z][a-z]{2}, \d{4}) - (\d{2} [A-Z][a-z]{2}, \d{4})")
CARD_NO = re.compile(r"(\d{6})X{6}(\d{4})")
SUMMARY = re.compile(r"^C([\d,]+\.\d{2})\s+C([\d,]+\.\d{2})\s+C([\d,]+\.\d{2})\s+C([\d,]+\.\d{2})$", re.M)
LIMITS = re.compile(r"^C([\d,]+)\s+C([\d,]+)\s+C([\d,]+)$", re.M)
COINS = re.compile(r"^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", re.M)


def detect(text):
    """An HDFC Bank card statement: names the bank and carries a `dd Mon, yyyy - dd Mon, yyyy` billing period."""
    return "HDFC BANK" in text.upper() and "Billing Period" in text and bool(PERIOD.search(text))


def _money(s):
    return float(s.replace(",", ""))


def _long_date(s):
    return datetime.strptime(s.replace(",", ""), "%d %b %Y").date().isoformat()


def _kind(desc, credit):
    u = desc.upper()
    if credit:
        if "PAYMENT" in u or "BPPY" in u or "BBPS" in u or "NEFT" in u or "IMPS" in u:
            return "payment"
        if "CASHBACK" in u or "WAIVER" in u:
            return "cashback"
        return "refund"           # a provisional credit reverses a UPI debit; a merchant credit is a refund
    if any(u.startswith(k) for k in ("GST", "IGST", "CGST", "SGST", "LATE PAYMENT", "FINANCE CHARGE", "ANNUAL FEE",
                                      "JOINING FEE", "MEMBERSHIP", "CASH ADVANCE FEE", "OVERLIMIT")):
        return "fee"
    return "spend"


def _records(text):
    """Transaction records: a date-and-time line, plus the lines that wrap until the amount appears."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        m = DATE_TIME.match(lines[i].strip())
        if not m:
            i += 1
            continue
        rec = lines[i].strip()
        j = i
        while not AMOUNT.search(rec) and j + 1 < len(lines) and j - i < 3:   # a wrapped line: join it on
            j += 1
            rec += " " + lines[j].strip()
        out.append(rec)
        i = j + 1
    return out


def _parse_record(rec):
    m = DATE_TIME.match(rec)
    d, hhmm, rest = m.groups()
    t = LINE_TAIL.match(rest)
    if not t:
        raise ValueError(f"unreadable transaction: {rec[:90]}")
    desc = re.sub(r"\s+", " ", t.group("desc")).strip()
    ref = re.search(r"\(Ref#\s*([A-Z0-9]+)\)", desc)
    credit = bool(t.group("credit"))
    kind = _kind(desc, credit)
    day = datetime.strptime(d, "%d/%m/%Y").date().isoformat()
    return {"tx_date": day, "ref": hhmm + (":" + ref.group(1) if ref else ""), "detail": desc,
            "amount": _money(t.group("amt")), "dc": "C" if credit else "D", "kind": kind,
            "points": int(t.group("coins") or 0), "ccy": "",
            "merchant": re.sub(r"^UPI-", "", desc), "city": "", "emi": 0,
            "is_spend": int(not credit and kind == "spend")}


def _after(label, text):
    """The first non-empty line after a label line (the extractor puts a label and its value on separate lines)."""
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if l == label:
            return next((x for x in lines[i + 1:i + 4] if x), "")
    return ""


def parse(text):
    """Parse one HDFC statement into a list with one entry (the common shape), or raise ValueError."""
    pm = PERIOD.search(text)
    if not pm:
        raise ValueError("no billing period found - is this an HDFC Bank statement?")
    sm = SUMMARY.search(text)
    if not sm:
        raise ValueError("the statement's previous dues, payments, purchases and finance charges did not parse")
    prev_dues, payments, purchases, finance = (_money(g) for g in sm.groups())

    rows = [_parse_record(r) for r in _records(text)]
    debits = round(sum(r["amount"] for r in rows if r["dc"] == "D"), 2)
    credits = round(sum(r["amount"] for r in rows if r["dc"] == "C"), 2)
    # The proof that the sign convention and the line reading are right: the lines add up to the printed totals.
    if abs(debits - (purchases + finance)) > 1 or abs(credits - payments) > 1:
        raise ValueError(f"transactions add up to debits {debits:,.2f} / credits {credits:,.2f} but the statement says "
                         f"{purchases + finance:,.2f} / {payments:,.2f} - refusing to import a partial statement")

    closing = round(prev_dues - payments + purchases + finance, 2)
    due_text = _after("DUE DATE", text)
    due = _long_date(due_text) if re.fullmatch(r"\d{2} [A-Z][a-z]{2}, \d{4}", due_text) else None   # "Nil" when nothing is due
    total_due = _money(_after("TOTAL AMOUNT DUE", text).lstrip("C") or "0")

    cm = COINS.search(text)
    coins = tuple(int(g) for g in cm.groups()) if cm else None            # opening, earned, transferred, lapsed
    earned = coins[1] if coins else None
    balance = (coins[0] + coins[1] - coins[2] - coins[3]) if coins else None
    # Base NeuCoins sit on the lines; bonus ones (partner brands, categories) are only in the total.
    if earned is not None and sum(r["points"] for r in rows) > earned:
        for r in rows:
            r["points"] = 0              # the lines contradict the printed total: keep the total only

    lm = LIMITS.search(text)
    card_no = CARD_NO.search(text)
    product = re.search(r"(Tata Neu [A-Za-z ]+?) HDFC Bank Credit Card Statement", text)
    stmt = _long_date(pm.group(2))
    return [{
        "card": {"issuer": "HDFC Bank", "last4": card_no.group(2) if card_no else "",
                 "name": (product.group(1).strip() + " HDFC") if product else "HDFC Credit Card",
                 "profile": "hdfc_neu" if product else "generic"},
        "kind": "cycle", "validation": "total",
        "period_from": _long_date(pm.group(1)), "period_to": stmt,
        "stmt_date": stmt, "due_date": due,
        "total_due": total_due, "min_due": 0.0,
        "credit_limit": _money(lm.group(1)) if lm else 0.0, "cash_limit": 0.0,
        "available_credit": _money(lm.group(2)) if lm else 0.0,
        "credits": credits, "purchases": round(sum(r["amount"] for r in rows if r["is_spend"]), 2),
        "fees": round(sum(r["amount"] for r in rows if r["kind"] == "fee"), 2),
        "cashback_reported": None, "points_earned": earned, "points_balance": balance,
        "closing_balance": closing,
        "txns": [{k: r[k] for k in ("tx_date", "detail", "merchant", "city", "amount", "dc", "emi", "is_spend",
                                    "kind", "ref", "ccy", "points")} for r in rows],
    }]
