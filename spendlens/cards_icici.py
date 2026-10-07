"""Parser for ICICI Bank credit-card statements (built against the Amazon Pay ICICI card).

These are not like SBI's monthly cycle statements. What ICICI issues here is a **yearly
transaction list** (`Statement Period 01/04/2025 TO 31/03/2026`): no account summary, no
purchases total, no limit, no statement or due dates. So the safeguard that protects the
SBI import - "the transactions must add up to the statement's own total" - has nothing to
compare against. The check used instead is **coverage**: every line that starts with a
date must parse, and the file is rejected if even one does not. A line that is silently
skipped would be a missing transaction, which is the failure that matters.

One file, several cards
-----------------------
The list is per *account*, not per card. It has a section for each card number
(`Card Number : 5241 XXXX XXXX 5007`) and often a pseudo-card `0000 XXXX XXXX 1001` for
account-level items such as reward-redemption fees. So `parse` returns a list, one entry per
real card. Account-level rows are handed to the card that was in use on the date. Card
numbers also change over time as cards are re-issued (a file here holds ...7000, ...7018 and
...5007 of one card), which is why each entry carries the first digits and the dates it was
active: `cards.resolve_card` uses them to recognise a re-issue.

Line format
-----------
    07-APR-25 BD015097BAHAAAN0CSXV BBPS Payment received 0.00 -4,500.00
    02-APR-25 74766515092513861261094 IND*AMAZON.IN - GROCER
    HTTP://WWW.AM IN
    0.00 737.00

date, a reference number (absent on tax lines), a description that may wrap onto the next
lines, an optional currency, an international amount (0.00 when domestic) and the rupee
amount. **Charges are positive and credits negative**, the reverse of what a reader might
assume. A record therefore runs from one date-led line to the next.

What the lines mean
-------------------
Besides purchases there are payments (four spellings), the iShop cashback, tax and fee lines
and EMI instalments. An EMI conversion is booked as: the purchase stays, a same-day credit
reverses it, and principal, interest and IGST arrive month by month. Real statements get
messier than that - a re-billed purchase, two conversions and a foreclosure with partial
reversals inside one week of December 2023 - so this parser does **not** try to pair each
reversal with its purchase. That would be guessing at intent. It relies on what is always
true instead: every line is a billed debit or a credit, and the cash adds up.

    net spend = merchant debits - merchant credits + EMI principal instalments

The converted purchase is refunded out and its instalments are counted back in, so an EMI
item counts once and is spread over the months it was actually paid (a cash view, which is
also what matters for deciding when to pay). Interest, IGST and processing fees are costs,
not spend; their reversals are negative costs.
"""
import re
from collections import Counter
from datetime import datetime

START = re.compile(r"^\d{2}-[A-Z]{3}-\d{2}\s")
# Page furniture repeated on every page, which must not be glued onto a transaction.
NOISE = ("The category of service", "RegistrationNo", "REGISTERED OFFICE", "This is an authenticated",
         "TRANSACTION DETAILS", "Card Number", "Date Ref. Number", "amount Amount")
END = ("Sincerely", "Important Messages")
RECORD = re.compile(
    r"^(\d{2}-[A-Z]{3}-\d{2})\s+(?:(\d[\w]*|[A-Z0-9_]{8,})\s+)?(.*?)\s+(?:([A-Z]{3})\s+)?"
    r"([\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})$")
PERIOD = re.compile(r"Statement Period\s*(\d{2}/\d{2}/\d{4}) TO (\d{2}/\d{2}/\d{4})")
SECTION = re.compile(r"^Card Number : (\d{4}) X{4} X{4} (\d{4})")
HEADER_ACCOUNT = re.compile(r"(\d{4}) X{4} X{4} (\d{4})\s*\n\s*Statement Period")
ACCOUNT_LEVEL = "0000"  # the pseudo-card that carries account-level items


def detect(text):
    """An ICICI statement names the bank and carries a `Statement Period dd/mm/yyyy TO ...` line."""
    return "ICICI BANK" in text.upper() and bool(PERIOD.search(text))


def _date(s):
    return datetime.strptime(s.title(), "%d-%b-%y").date().isoformat()


def _d(s):
    return datetime.strptime(s, "%d/%m/%Y").date().isoformat()


def _money(s):
    return float(s.replace(",", ""))


def _kind(desc):
    """What a line is, from its description."""
    u = desc.upper()
    if "PAYMENT RECEIVED" in u or u.startswith(("UPI PAYMENT", "NEFT PAYMENT", "IMPS PAYMENT")) or "BBPS PAYMENT" in u:
        return "payment"
    if "CASHBACK" in u:
        return "cashback"
    if "PRINCIPAL" in u and "REVERSAL" not in u:
        return "emi_principal"
    # "FEE " / "FEELEVY" are bank charges; "FEES COLLECTION A/C" is a school paying its fees, i.e. a purchase
    if (u.startswith(("IGST", "CGST", "SGST", "GST", "FEE ", "FEELEVY", "LATE", "ANNUAL", "MEMBERSHIP", "REVERSAL", "EMI PROCESSING"))
            or "PROCESSING FEE" in u or "FINANCE CHARGE" in u or "OVERLIMIT" in u or "INTEREST AMOUNT" in u):
        return "fee"
    return "merchant"


def _merchant(desc):
    """The merchant name from a description, without the URL or country code."""
    d = re.sub(r"HTTPS?://\S*", "", desc, flags=re.I)
    d = re.sub(r"\s+IN$", "", d.strip())
    return re.sub(r"\s{2,}", " ", d).strip()


def _records(text):
    """Group the text into records: one per date-led line, plus the lines that wrap after it.

    Returns [(section, record_text)] where section is the (first4, last4) of the card whose
    `Card Number :` heading the record sits under.
    """
    recs, cur, section = [], None, None
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            section = (m.group(1), m.group(2))
            continue
        if START.match(line):
            cur = [line]
            recs.append((section, cur))
        elif line.startswith(END):
            cur = None
        elif cur is not None and not line.startswith(NOISE):
            cur.append(line)
    return [(sec, " ".join(p.strip() for p in r)) for sec, r in recs]


def _classify_rows(rows):
    """Give each raw row its kind, merchant and spend flag."""
    for r in rows:
        k = _kind(r["detail"])
        if k == "merchant":
            k = "spend" if r["dc"] == "D" else "refund"
        r["kind"] = k
        r["emi"] = int(k == "emi_principal")
        r["city"] = ""
        r["merchant"] = ("EMI instalment" if k == "emi_principal" else
                         _merchant(r["detail"]) if k in ("spend", "refund") else r["detail"])
        # Rows that count as spend: purchases and EMI instalments.
        r["is_spend"] = int(r["dc"] == "D" and k in ("spend", "emi_principal"))


def _owner(day, spans, header, sizes):
    """Which card an account-level row belongs to: the one in use on that date.

    Several cards can be in use at once (two in 2025 here), so a tie goes to the card the
    statement is addressed to, then to the busiest. A date outside every card's span goes to the
    nearest one.
    """
    live = [k for k, (lo, hi) in spans.items() if lo <= day <= hi]
    if not live:
        return min(spans, key=lambda k: min(abs((_to_date(day) - _to_date(spans[k][0])).days),
                                            abs((_to_date(day) - _to_date(spans[k][1])).days)))
    if len(live) == 1:
        return live[0]
    return header if header in live else max(live, key=lambda k: sizes[k])


def _to_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").date()


def _build(rows, section, period, text):
    net = lambda *kinds: sum(r["amount"] if r["dc"] == "D" else -r["amount"] for r in rows if r["kind"] in kinds)
    days = Counter(int(r["tx_date"][8:]) for r in rows if r["kind"] == "emi_principal")
    dates = [r["tx_date"] for r in rows]
    return {
        "card": {"issuer": "ICICI Bank", "last4": section[1], "bin": section[0],
                 "name": f"ICICI Bank \u00b7\u00b7\u00b7{section[1]}", "profile": "generic",
                 "first_seen": min(dates), "last_seen": max(dates)},
        "kind": "year", "validation": "coverage",
        "period_from": _d(period.group(1)), "period_to": _d(period.group(2)),
        "stmt_date": _d(period.group(2)), "due_date": None,
        "total_due": 0.0, "min_due": 0.0, "credit_limit": 0.0, "cash_limit": 0.0,
        "available_credit": 0.0,
        "credits": round(sum(r["amount"] for r in rows if r["kind"] == "payment"), 2),
        "purchases": round(net("spend", "refund", "emi_principal"), 2),
        "fees": round(net("fee"), 2), "cashback_reported": None,
        # The statement day is not printed. EMI instalments and their tax post on the statement date.
        "statement_day_hint": days.most_common(1)[0][0] if days else None,
        "txns": [{k: r[k] for k in ("tx_date", "detail", "merchant", "city", "amount", "dc",
                                    "emi", "is_spend", "kind", "ref", "ccy")} for r in rows],
    }


def parse(text):
    """Parse one ICICI statement into a list of the common shape, one per card in the file.

    Raises ValueError if the file is not one of these statements or any line is unreadable.
    """
    period = PERIOD.search(text)
    if not period:
        raise ValueError("no statement period found - is this an ICICI Bank statement?")
    records = _records(text)
    if not records:
        raise ValueError("no transactions found")

    rows, unread = [], []
    for section, rec in records:
        m = RECORD.match(rec)
        if not m:
            unread.append(rec[:90])
            continue
        dt, ref, desc, ccy, intl, amt = m.groups()
        signed = _money(amt)
        # A 3-letter capital word before the amounts is a currency only when there is a foreign amount;
        # otherwise it is the tail of the description ("... THANK YOU", "FASTAG IMB"). It is still left
        # out of `detail`, exactly as before: a row's de-duplication hash includes `detail`, so keeping
        # every stored row's identity stable matters more than a tidier description.
        if ccy and _money(intl) <= 0:
            ccy = ""
        rows.append({"tx_date": _date(dt), "ref": ref or "", "detail": desc.strip(), "section": section,
                     "amount": abs(signed), "dc": "C" if signed < 0 else "D", "ccy": ccy or ""})
    # The coverage check: a line that cannot be read is a transaction that would go missing.
    if unread:
        raise ValueError(f"{len(unread)} line(s) could not be read, e.g. '{unread[0]}' - "
                         "refusing to import a partial statement")

    rows = [r for r in rows if r["amount"] > 0]  # zero-amount lines are EMI-conversion markers
    _classify_rows(rows)

    by = {}
    for r in rows:
        by.setdefault(r["section"] or ("", ""), []).append(r)
    cards_ = {k: v for k, v in by.items() if k[0] != ACCOUNT_LEVEL}
    if not cards_:                      # a file that is only the account-level section
        cards_ = by
    else:
        spans = {k: (min(r["tx_date"] for r in v), max(r["tx_date"] for r in v)) for k, v in cards_.items()}
        sizes = {k: len(v) for k, v in cards_.items()}
        hm = HEADER_ACCOUNT.search(text)
        header = next((k for k in cards_ if hm and k == (hm.group(1), hm.group(2))), None)
        for key, v in by.items():
            if key[0] == ACCOUNT_LEVEL:
                for r in v:
                    cards_[_owner(r["tx_date"], spans, header, sizes)].append(r)
    return [_build(sorted(v, key=lambda r: r["tx_date"]), k, period, text) for k, v in sorted(cards_.items())]
