"""Parser for American Express activity exports (Excel), built against the SmartEarn card.

This is not a statement but an *activity download*: a workbook with a `Transaction Details` sheet (one row
per transaction) and a `Transaction Summary` sheet that totals the whole file. There is no billing cycle, no
due date and no reward balance in it, but the summary gives the same proof a printed statement does: the
charges must add up to the summary's `Charges` and the payments and credits to its `Payments & Credits`.

`cards.read_pdf` turns a workbook into text (one line per row, cells separated by tabs, a `#SHEET` line before
each sheet) so it goes through the same registry as the PDF parsers.

A row is
    Date (mm/dd/yyyy), Description, Amount, Extended Details, Appears On Your Statement As, Address,
    City/State, Zip Code, Country, Reference, Category
with **charges positive and credits negative**. Every row has a reference number, so the same export taken
twice, or two exports that overlap, de-duplicate on it. Amex also categorises each charge (`Travel-Rail
Services`), which no other card here provides, so the category is kept.

"Pay with Points Credit" rows are Membership Rewards points spent as a bill credit: realised reward value, not
points earned (the export does not say how many were earned), so the dashboard calls it *redeemed*.
"""
import re
from datetime import datetime

TITLE = re.compile(r"^(?P<name>.*?)\s*/\s*(?P<from>[A-Z][a-z]{2} \d{2}, \d{4}) to (?P<to>[A-Z][a-z]{2} \d{2}, \d{4})$")
ACCOUNT = re.compile(r"X{2,}-X{2,}-(\d{4,5})")
FEE_WORDS = ("CONVENIENCE FEE", "ANNUAL FEE", "MEMBERSHIP FEE", "LATE PAYMENT", "FINANCE CHARGE", "INTEREST CHARGE", "OVERLIMIT")


def detect(text):
    """An Amex activity workbook: names American Express and has the transaction columns."""
    return "AMERICAN EXPRESS" in text.upper() and "Appears On Your Statement As" in text and "#SHEET" in text


def _sheets(text):
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("#SHEET\t"):
            cur = out.setdefault(line.split("\t", 1)[1], [])
        elif cur is not None and line.strip():
            cur.append(line.split("\t"))
    return out


def _date(s):
    return datetime.strptime(s, "%m/%d/%Y").date().isoformat()


def _long(s):
    return datetime.strptime(s, "%b %d, %Y").date().isoformat()


def _kind(desc, amount):
    u = desc.upper()
    if amount < 0:
        if "PAYMENT RECEIVED" in u:
            return "payment"
        if "PAY WITH POINTS" in u:
            return "cashback"          # points spent as a bill credit: realised reward value
        return "refund"
    if u.startswith(("GST", "IGST", "CGST", "SGST")) or any(k in u for k in FEE_WORDS):
        return "fee"
    return "spend"


def _merchant(desc):
    """The shop, without the payment aggregator in front of it (`Cashfree*Swiggy   Bangal`) or padding."""
    return re.sub(r"\s+", " ", re.sub(r"^[A-Za-z]{2,12}\*", "", desc)).strip()


def parse(text):
    """Parse one activity workbook. Returns a list with one entry, or raises ValueError."""
    sheets = _sheets(text)
    rows = sheets.get("Transaction Details")
    if not rows:
        raise ValueError("no Transaction Details sheet found - is this an Amex activity download?")
    title = TITLE.match(rows[0][1].strip()) if len(rows[0]) > 1 else None
    if not title:
        raise ValueError("the report title with its period was not found")
    head = next((i for i, r in enumerate(rows) if r and r[0] == "Date" and "Amount" in r), None)
    if head is None:
        raise ValueError("the transaction table header was not found")
    cols = {name: i for i, name in enumerate(rows[head])}
    need = ("Description", "Amount", "Reference")
    if any(n not in cols for n in need):
        raise ValueError("the transaction table is missing a column: " + ", ".join(n for n in need if n not in cols))
    account = next((m.group(1) for r in rows[:head] for c in r for m in [ACCOUNT.search(c)] if m), "")

    def cell(r, name):
        i = cols.get(name)
        return r[i].strip() if i is not None and i < len(r) else ""

    txns = []
    for r in rows[head + 1:]:
        if not r or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", r[0].strip()):
            continue
        amount = float(cell(r, "Amount"))
        desc = re.sub(r"\s+", " ", cell(r, "Description"))
        kind = _kind(desc, amount)
        txns.append({"tx_date": _date(r[0].strip()), "detail": desc, "merchant": _merchant(desc), "city": cell(r, "City/State"),
                     "amount": abs(amount), "dc": "C" if amount < 0 else "D", "emi": 0, "kind": kind,
                     "is_spend": int(amount > 0 and kind == "spend"), "ref": cell(r, "Reference"),
                     "ccy": "" if cell(r, "Country").upper() in ("", "INDIA") else cell(r, "Country"),
                     "points": 0, "category": cell(r, "Category")})
    if not txns:
        raise ValueError("no transactions found")

    # The proof: the rows must add up to the workbook's own summary.
    summary = {r[0]: r[1] for r in sheets.get("Transaction Summary", []) if len(r) > 1 and r[0]}
    charges = round(sum(t["amount"] for t in txns if t["dc"] == "D"), 2)
    credits = round(sum(t["amount"] for t in txns if t["dc"] == "C"), 2)
    try:
        want_c, want_p = float(summary["Charges"]), -float(summary["Payments & Credits"])
    except (KeyError, ValueError):
        raise ValueError("the Transaction Summary sheet (Charges, Payments & Credits) was not found - cannot verify the file")
    if abs(charges - want_c) > 0.5 or abs(credits - want_p) > 0.5:
        raise ValueError(f"rows add up to charges {charges:,.2f} / credits {credits:,.2f} but the summary says "
                         f"{want_c:,.2f} / {want_p:,.2f} - refusing to import a partial file")

    end = _long(title.group("to"))
    return [{
        "card": {"issuer": "American Express", "last4": account, "name": title.group("name").strip() or "Amex card",
                 "profile": "amex_smartearn" if "SMARTEARN" in title.group("name").upper() else "generic"},
        "kind": "year", "validation": "total",
        "period_from": _long(title.group("from")), "period_to": end, "stmt_date": end, "due_date": None,
        "total_due": 0.0, "min_due": 0.0, "credit_limit": 0.0, "cash_limit": 0.0, "available_credit": 0.0,
        "credits": round(sum(t["amount"] for t in txns if t["kind"] == "payment"), 2),
        "purchases": round(sum(t["amount"] for t in txns if t["is_spend"]), 2),
        "fees": round(sum(t["amount"] for t in txns if t["kind"] == "fee"), 2),
        "cashback_reported": None, "txns": txns,
    }]
