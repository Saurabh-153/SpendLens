"""Credit cards: statement import, the reward engine and the dashboard.

Built against real statements: ten monthly SBI CASHBACK Card statements (Dec 2025 - Sep 2026)
and five yearly ICICI Amazon Pay lists (FY2021 - FY2025).

Layout of the card code
-----------------------
- `cards.py` (this file): the SBI parser, the parser registry and the optional Claude fallback,
  reward classification and the earn engine, storage, and the dashboard payload.
- `cards_icici.py`: the ICICI Bank parser.
- `card_float.py`: when to pay - billing cycle, payment matching, what early payment costs.

How a statement is checked
--------------------------
A statement is imported completely or not at all. SBI prints a purchases total that the parsed
transactions must equal. ICICI's yearly list prints no totals, so every date-led line must parse
instead. A Claude-read statement must meet the SBI-style total check.

Cards differ in one place: `PROFILES`. A profile names the reward classes, the rules that sort a
merchant into a class, the default rates, and whether EMI earns. Everything else is shared.

What the real statements established
------------------------------------
- On SBI, spends converted to EMI *do* earn cashback (the statements only reconcile if they do);
  on Amazon Pay ICICI they do not, by the card's published terms.
- SBI paid Rs 2,848 in one cycle, which disproves the Rs 2,000 cap some comparison sites quote.
  The real cap was never reached, so it is a setting.
- Refunds take their reward back. Modelling that, and keeping identical same-day lines, brought
  computed cashback within 0.2% of what SBI paid.
- Neither bank's statement says which spend was online; that is inferred per merchant, and the
  computed figure is always shown next to the reported one where a statement prints it.
"""
import calendar
import json
import os
import re
from datetime import date, datetime, timedelta

import card_float as cf
import cards_amex
import cards_bob
import cards_hdfc
import cards_icici

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

# A transaction line. The merchant / city / country columns are space padded.
TXN_RE = re.compile(r"^(\d{2}) ([A-Z][a-z]{2}) (\d{2}) (.+?) ([\d,]+\.\d{2}) ([CD])$")
PERIOD_RE = re.compile(r"Statement Period:\s*(\d{2} [A-Z][a-z]{2} \d{2}) to (\d{2} [A-Z][a-z]{2} \d{2})")
# Summary values and the two long-form dates, in the order the statement prints them.
SUMMARY_RE = re.compile(r"^(?:[\d,]+\.\d{2}|\d{2} [A-Z][a-z]{2} \d{4})$", re.M)
MONEY_RE = re.compile(r"^[\d,]+\.\d{2}$")

# Lines that are not spending: payments in, the cashback credit, fees.
NOT_SPEND = ("PAYMENT RECEIVED", "CARD CASHBACK", "ANNUAL FEE", "REVERSAL", "REFUND",
             "FINANCE CHARGE", "LATE PAYMENT", "GST", "INTEREST CHARGE")

ONLINE, OFFLINE, EXCLUDED = "online", "offline", "excluded"

#: Classification rules, first match wins. `kind` is "prefix" (an aggregator tag before
#: the merchant name), "contains" or "regex". Order matters: exclusions come first,
#: because an excluded category outranks being online.
#:
#: Exclusions follow the card's published terms - fuel, utilities, rent, wallet loads,
#: gift vouchers, jewellery, railways and education earn nothing.
DEFAULT_RULES = [
    # --- earns nothing ---
    (EXCLUDED, "contains", "PETROL"), (EXCLUDED, "contains", "FUEL"),
    (EXCLUDED, "contains", "HPCL"), (EXCLUDED, "contains", "IOCL"),
    (EXCLUDED, "contains", "BHARAT PETRO"), (EXCLUDED, "contains", "SHELL"),
    (EXCLUDED, "contains", "BROADBAND"), (EXCLUDED, "contains", "TATA PLAY"),
    (EXCLUDED, "contains", "AIRTEL"), (EXCLUDED, "contains", "JIO"),
    (EXCLUDED, "contains", "ELECTRICITY"), (EXCLUDED, "contains", "BESCOM"),
    (EXCLUDED, "contains", "GAS"), (EXCLUDED, "contains", "RENT"),
    (EXCLUDED, "contains", "WALLET"), (EXCLUDED, "contains", "GYFTR"),
    (EXCLUDED, "contains", "VOUCHER"), (EXCLUDED, "contains", "GIFT CARD"),
    (EXCLUDED, "contains", "IRCTC"), (EXCLUDED, "contains", "RAILWAY"),
    (EXCLUDED, "contains", "INSURANCE"), (EXCLUDED, "contains", "LIC OF INDIA"),
    (EXCLUDED, "contains", "JEWELL"), (EXCLUDED, "contains", "TANISHQ"),
    (EXCLUDED, "contains", "SCHOOL"), (EXCLUDED, "contains", "TUITION"),

    # --- online: a payment aggregator in front of the merchant means a web checkout ---
    (ONLINE, "regex", r"^(PYU|PAYU|PPSL|PTM|PAY|RAZ|RSP|CAS|EAS|IND|BPY|CCA|PHONEPE)\*"),
    (ONLINE, "regex", r"^WWW|WWW$|\.COM|\.IN\b"),
    # --- online: known web merchants ---
    (ONLINE, "contains", "AMAZON"), (ONLINE, "contains", "ASSPL"),
    (ONLINE, "contains", "FLIPKART"), (ONLINE, "contains", "MYNTRA"),
    (ONLINE, "contains", "MEESHO"), (ONLINE, "contains", "AJIO"),
    (ONLINE, "contains", "NYKAA"), (ONLINE, "contains", "FIRSTCRY"),
    (ONLINE, "contains", "BIGBASKET"), (ONLINE, "contains", "ZEPTO"),
    (ONLINE, "contains", "BLINKIT"), (ONLINE, "contains", "INSTAMART"),
    (ONLINE, "contains", "SWIGGY"), (ONLINE, "contains", "BUNDL"),
    (ONLINE, "contains", "ZOMATO"), (ONLINE, "contains", "ETERNAL"),
    (ONLINE, "contains", "DELIGHTFUL GOURMET"), (ONLINE, "contains", "LICIOUS"),
    (ONLINE, "contains", "UBER"), (ONLINE, "contains", "OLA "),
    (ONLINE, "contains", "RAPIDO"), (ONLINE, "contains", "YATRA"),
    (ONLINE, "contains", "MAKEMYTRIP"), (ONLINE, "contains", "IXIGO"),
    (ONLINE, "contains", "GOOGLEPLAY"), (ONLINE, "contains", "GOOGLE PLAY"),
    (ONLINE, "contains", "NETFLIX"), (ONLINE, "contains", "SPOTIFY"),
    (ONLINE, "contains", "TIMESPRIME"), (ONLINE, "contains", "UDEMY"),
    (ONLINE, "contains", "GITHUB"), (ONLINE, "contains", "1MG"),
    (ONLINE, "contains", "PHARMEASY"), (ONLINE, "contains", "NETMEDS"),
    (ONLINE, "contains", "APOLLO PHARMAC"), (ONLINE, "contains", "FNP"),
]

#: Merchant aliases, so the dashboard groups what is really one shop. Matched as a
#: substring of the normalised merchant; the first hit wins.
ALIASES = [
    ("Amazon", ("AMAZON", "ASSPL")), ("Flipkart", ("FLIPKART",)), ("Myntra", ("MYNTRA",)),
    ("Swiggy", ("SWIGGY", "BUNDL", "INSTAMART")), ("Zomato", ("ZOMATO", "ETERNAL")),
    ("BigBasket", ("BIGBASKET",)), ("Zepto", ("ZEPTO",)), ("Licious", ("LICIOUS", "DELIGHTFUL GOURMET")),
    ("Meesho", ("MEESHO", "FASHNEAR")), ("FirstCry", ("FIRSTCRY",)), ("Tata 1mg", ("1MG",)),
    ("Office canteen", ("COMPASS INDIA",)), ("Uber", ("UBER",)), ("Yatra", ("YATRA",)),
    ("Tata Play", ("TATA PLAY",)), ("DMart", ("AVENUE SUPERMARTS",)),
    ("Google Play", ("GOOGLEPLAY",)), ("Lifestyle", ("LIFE STYLE INTERNATIO",)),
    ("EMI instalments", ("EMI INSTALMENT",)),
]


# ---------------------------------------------------------------- parsing

def _money(s):
    return float(s.replace(",", ""))


def _iso(day, mon, yy):
    return date(2000 + int(yy), MONTHS[mon], int(day)).isoformat()


def _iso_long(s):
    return datetime.strptime(s, "%d %b %Y").date().isoformat()


def split_detail(detail):
    """`PYU*FLIPKART INTERNET  Bangalore  IND (Pay in EMIs)` -> merchant, city, emi flag."""
    emi = "(Pay in EMIs)" in detail
    d = detail.replace("(Pay in EMIs)", "").strip()
    d = re.sub(r"\s+(IND|[A-Z]{3})$", "", d).strip()
    parts = [p.strip() for p in re.split(r"\s{2,}", d) if p.strip()]
    merchant = parts[0] if parts else d
    city = parts[1] if len(parts) > 1 else ""
    return merchant.strip(), city, emi


def _is_xlsx(source):
    """An .xlsx workbook is a zip file: look at the first bytes, not the name."""
    try:
        if isinstance(source, str):
            with open(source, "rb") as f:
                head = f.read(4)
        else:
            pos = source.tell()
            head = source.read(4)
            source.seek(pos)
        return head == b"PK\x03\x04"
    except Exception:
        return False


def _read_workbook(source, label):
    """Render a workbook as text: a `#SHEET` line, then one tab-separated line per row. A parser reads
    that the same way it reads a PDF's text, so spreadsheets go through the same registry."""
    import warnings
    import openpyxl
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")      # exports from some banks carry no default style
            wb = openpyxl.load_workbook(source, data_only=True)
    except Exception:
        raise ValueError(f"{label} is not a readable spreadsheet (a password-protected or old .xls file cannot be read)")
    lines = []
    for ws in wb.worksheets:
        lines.append(f"#SHEET\t{ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else re.sub(r"[\t\r\n]+", " ", str(c)) for c in row]
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                lines.append("\t".join(cells))
    return "\n".join(lines)


def _garbled(text):
    """True when the text is mostly single characters on their own lines (unreadable as extracted)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return len(lines) > 200 and sum(len(l) for l in lines) / len(lines) < 3


def read_pdf(source, password="", name=""):
    """Extract the text of one statement from a path or a file-like object.

    Raises ValueError for a wrong password or a file that is not a readable PDF.
    """
    import logging
    import pypdf  # imported lazily: only an import needs it
    # SBI's statements embed a CFF font pypdf cannot fully decode; it warns once per page
    # and extracts the text correctly anyway.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    label = name or (os.path.basename(source) if isinstance(source, str) else "the file")
    if _is_xlsx(source):
        return _read_workbook(source, label)
    try:
        reader = pypdf.PdfReader(source)
    except Exception:
        raise ValueError(f"{label} is not a readable PDF or spreadsheet")
    if reader.is_encrypted and not reader.decrypt(password or ""):
        raise ValueError(f"wrong password for {label}")
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    if _garbled(text):
        # Some generators lay each glyph out separately, which the default extraction returns one
        # character per line. The layout-aware extraction keeps the columns together.
        text = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in reader.pages)
    if not text.strip():
        raise ValueError(f"{label} has no text layer (a scanned image?) - it cannot be read")
    return text


def _row_kind(dc, upper, spend):
    """What a statement line is: spend, payment, cashback, refund or fee."""
    if spend:
        return "spend"
    if dc == "C":
        return "payment" if "PAYMENT RECEIVED" in upper else "cashback" if "CARD CASHBACK" in upper else "refund"
    return "fee"


def detect_sbi(text):
    """Does this look like an SBI Card statement?"""
    return "SBI Card" in text and bool(PERIOD_RE.search(text))


def parse_statement(text):
    """Pull the summary, the cashback figure and the transactions out of one statement.

    Returns a dict, or raises ValueError when the parse cannot be trusted.
    """
    period = PERIOD_RE.search(text)
    if not period:
        raise ValueError("no statement period found - is this an SBI Card statement?")

    head = text.split("TRANSACTIONS FOR")[0]
    vals = SUMMARY_RE.findall(head)
    if len(vals) < 11 or not all(MONEY_RE.match(v) for v in vals[:9]):
        raise ValueError("the account summary block did not parse")
    dates = [v for v in vals[9:] if not MONEY_RE.match(v)]
    if not dates:
        raise ValueError("no statement date found")

    txns = []
    for line in text.splitlines():
        m = TXN_RE.match(line.strip())
        if not m:
            continue
        dd, mon, yy, detail, amt, dc = m.groups()
        detail = detail.strip()
        upper = detail.upper()
        merchant, city, emi = split_detail(detail)
        spend = dc == "D" and not any(k in upper for k in NOT_SPEND)
        txns.append({"tx_date": _iso(dd, mon, yy), "detail": detail, "merchant": merchant,
                     "city": city, "amount": _money(amt), "dc": dc, "emi": int(emi), "ref": "",
                     "is_spend": int(spend), "kind": _row_kind(dc, upper, spend)})

    # The statement's own figure for what was spent. This is the check that the parse worked.
    purchases = _money(vals[7])
    parsed = round(sum(t["amount"] for t in txns if t["is_spend"]), 2)
    if abs(parsed - purchases) > 1:
        raise ValueError(f"parsed spend {parsed:,.2f} does not match the statement's "
                         f"{purchases:,.2f} - refusing to import a partial statement")

    # The cashback for this cycle is printed as a bare integer after the T&C note.
    cashback = None
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if "T&C Apply" in l:
            for nxt in lines[i + 1:i + 5]:
                if re.fullmatch(r"\d+", nxt):
                    cashback = int(nxt)
                    break
            break

    last4 = re.search(r"X{4} X{4} X{4} X*(\d{2,4})", text)
    return {
        "card": {"issuer": "SBI Card", "last4": last4.group(1) if last4 else "", "name": "CASHBACK SBI Card",
                 "profile": "sbi_cashback"},
        "kind": "cycle", "validation": "total",
        "period_from": _iso(*period.group(1).split()),
        "period_to": _iso(*period.group(2).split()),
        "total_due": _money(vals[0]), "min_due": _money(vals[1]),
        "credit_limit": _money(vals[2]), "cash_limit": _money(vals[3]),
        "available_credit": _money(vals[4]),
        "credits": _money(vals[6]), "purchases": purchases, "fees": _money(vals[8]),
        "stmt_date": _iso_long(dates[0]),
        "due_date": _iso_long(dates[1]) if len(dates) > 1 else None,
        "cashback_reported": cashback, "txns": txns,
    }


# ---------------------------------------------------------------- parser registry

#: Formats with a hand-written parser: (name, detector, parser). A detector looks at the
#: extracted text and says whether the format is this one; the first match wins. Adding
#: a bank means writing one detector and one parser that returns the dict shape of
#: `parse_statement` and raises ValueError when its own arithmetic does not hold.
PARSERS = [("SBI Card", detect_sbi, parse_statement),
           ("ICICI Bank", cards_icici.detect, cards_icici.parse),
           ("Bank of Baroda", cards_bob.detect, cards_bob.parse),
           ("HDFC Bank", cards_hdfc.detect, cards_hdfc.parse),
           ("American Express", cards_amex.detect, cards_amex.parse)]

LLM_MODEL = "claude-sonnet-5-5"
LLM_MAX_CHARS = 60000  # a statement is ~40k characters; refuse anything wildly bigger


def llm_available():
    """The Claude fallback needs an API key in the environment. It is never stored."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


LLM_PROMPT = """You are extracting a credit-card statement into JSON. Reply with ONLY a JSON \
object, no prose and no code fences, shaped exactly like:
{"card": {"issuer": "bank name", "last4": "last digits of the card number", "name": "card product name"},
 "period_from": "YYYY-MM-DD", "period_to": "YYYY-MM-DD", "stmt_date": "YYYY-MM-DD",
 "due_date": "YYYY-MM-DD or null", "total_due": 0, "min_due": 0, "credit_limit": 0,
 "cash_limit": 0, "available_credit": 0, "credits": 0, "purchases": 0, "fees": 0,
 "cashback_reported": null,
 "txns": [{"tx_date": "YYYY-MM-DD", "detail": "the line as printed", "amount": 0,
           "dc": "D or C", "emi": false}]}
Rules: amounts are plain numbers in rupees (no commas). "purchases" is the statement's own
printed total of purchases/debits for the cycle. Every transaction line goes in "txns",
including payments received (dc "C") and fees. dc is "D" for money you owe, "C" for credits.
Do not invent, merge or skip lines. Use null for anything the statement does not state."""


def _llm_complete(text):
    """One call to Claude. Isolated so tests can replace it. Returns the raw reply text."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=LLM_MODEL, max_tokens=16000,
        messages=[{"role": "user", "content": f"{LLM_PROMPT}\n\nSTATEMENT TEXT:\n{text}"}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def parse_with_llm(text):
    """Ask Claude to read a statement no hand-written parser recognises.

    The reply is not trusted. Every field is type-checked, `is_spend` is derived here
    rather than taken from the model, and the same gate as every other format applies:
    the transactions must add up to the statement's own purchases figure, or the whole
    statement is rejected.
    """
    import json
    if not llm_available():
        raise ValueError("no ANTHROPIC_API_KEY is set, so the Claude fallback is unavailable")
    if len(text) > LLM_MAX_CHARS:
        raise ValueError("this statement is too large to send to Claude")
    raw = _llm_complete(text).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        d = json.loads(raw)
        iso = lambda s: date.fromisoformat(s).isoformat()
        txns = []
        for t in d["txns"]:
            detail = str(t["detail"]).strip()
            merchant, city, emi = split_detail(detail)
            amount, dc = float(t["amount"]), str(t["dc"]).upper()
            if dc not in ("C", "D") or amount < 0:
                raise ValueError("bad transaction")
            spend = dc == "D" and not any(k in detail.upper() for k in NOT_SPEND)
            txns.append({"tx_date": iso(t["tx_date"]), "detail": detail, "merchant": merchant,
                         "city": city, "amount": amount, "dc": dc, "ref": "",
                         "emi": int(bool(t.get("emi")) or emi), "is_spend": int(spend),
                         "kind": _row_kind(dc, detail.upper(), spend)})
        num = lambda k: float(d.get(k) or 0)
        info = d.get("card") or {}
        parsed = {
            "card": {"issuer": str(info.get("issuer") or "Unknown bank")[:40],
                     "last4": re.sub(r"\D", "", str(info.get("last4") or ""))[-4:],
                     "name": str(info.get("name") or "Credit card")[:60], "profile": "generic"},
            "kind": "cycle", "validation": "total",
            "period_from": iso(d["period_from"]), "period_to": iso(d["period_to"]),
            "stmt_date": iso(d.get("stmt_date") or d["period_to"]),
            "due_date": iso(d["due_date"]) if d.get("due_date") else None,
            "total_due": num("total_due"), "min_due": num("min_due"),
            "credit_limit": num("credit_limit"), "cash_limit": num("cash_limit"),
            "available_credit": num("available_credit"), "credits": num("credits"),
            "purchases": float(d["purchases"]), "fees": num("fees"),
            "cashback_reported": int(d["cashback_reported"]) if d.get("cashback_reported") is not None else None,
            "txns": txns,
        }
    except Exception as e:
        raise ValueError(f"Claude's reply could not be used ({type(e).__name__}) - nothing was imported")
    if not parsed["txns"]:
        raise ValueError("Claude found no transactions - nothing was imported")
    spent = round(sum(t["amount"] for t in txns if t["is_spend"]), 2)
    if abs(spent - parsed["purchases"]) > 1:
        raise ValueError(f"Claude's transactions add up to {spent:,.2f} but the statement says "
                         f"{parsed['purchases']:,.2f} - refusing to import a partial statement")
    return parsed


def parse_any(text, allow_llm=False):
    """Parse with the first matching hand-written parser; else, if allowed, with Claude.

    Returns (list of parsed statements, parser_name): one entry per card the file covers. Raises
    ValueError with a message the user can act on.
    """
    for name, detect, parse in PARSERS:
        if detect(text):
            out = parse(text)
            return (out if isinstance(out, list) else [out]), name   # one entry per card in the file
    if allow_llm:
        return [parse_with_llm(text)], "Claude"
    known = ", ".join(n for n, _, _ in PARSERS)
    raise ValueError(f"unrecognised statement format (built-in parsers: {known}). "
                     "Tick 'use Claude for unrecognised formats' to try reading it with Claude.")


# ---------------------------------------------------------------- classification

AMAZON, PARTNER, OTHER = "amazon", "partner", "other"

#: Amazon Pay ICICI. Published terms: 5% on Amazon for Prime members (3% without), 2% at
#: Amazon Pay partner merchants, 1% everywhere else, uncapped. Fuel, rent, EMI, education,
#: government and tax, international and precious-metal spends earn nothing. Which merchants
#: count as "partners" is the least certain part, so those rates are estimates; correcting a
#: merchant on the dashboard saves a rule.
AMAZON_RULES = [
    (EXCLUDED, "contains", "PETROL"), (EXCLUDED, "contains", "FUEL"), (EXCLUDED, "contains", "HPCL"),
    (EXCLUDED, "contains", "IOCL"), (EXCLUDED, "contains", "RENT"), (EXCLUDED, "contains", "SCHOOL"),
    (EXCLUDED, "contains", "TUITION"), (EXCLUDED, "contains", "UNIVERSITY"), (EXCLUDED, "contains", "JEWELL"),
    (EXCLUDED, "contains", "TANISHQ"), (EXCLUDED, "contains", "GOVT"),
    (PARTNER, "contains", "RECHARGE"), (PARTNER, "contains", "BILL P"), (PARTNER, "contains", "UTILITY"),
    (PARTNER, "contains", "IRCTC"), (PARTNER, "contains", "SWIGGY"), (PARTNER, "contains", "ZOMATO"),
    (PARTNER, "contains", "MAKEMYTRIP"),
    (AMAZON, "contains", "AMAZON"), (AMAZON, "contains", "ASSPL"),
]

#: ICICI Rubyx. Published terms (icici.bank.in): 4 reward points per Rs 100 on international spend,
#: 2 on domestic, 1 on utility and insurance, none on fuel; 3,000 points at Rs 3 lakh a year and 1,500
#: for every further lakh, up to 15,000 a year; 2 domestic lounge visits a quarter when the previous
#: quarter's spend exceeded Rs 75,000 (primary card only). The bank's page does not state a point
#: value; third-party pages say Rs 0.25, so it is an assumption and every rate here is editable.
#: Beyond fuel the exclusions are not published on that page, so only fuel is excluded.
INTERNATIONAL, DOMESTIC, UTILITY = "international", "domestic", "utility"
POINT_VALUE = 0.25
RUBYX_RULES = [
    (EXCLUDED, "contains", "PETROL"), (EXCLUDED, "contains", "FUEL"), (EXCLUDED, "contains", "HPCL"),
    (EXCLUDED, "contains", "IOCL"), (EXCLUDED, "contains", "BHARAT PETRO"), (EXCLUDED, "contains", "SHELL"),
    (UTILITY, "contains", "INSUR"), (UTILITY, "contains", "MAX LIFE"), (UTILITY, "contains", "HDFC LIFE"),
    (UTILITY, "contains", "POLICYBAZAAR"), (UTILITY, "contains", "AIRTEL"), (UTILITY, "contains", "JIO"),
    (UTILITY, "contains", "BESCOM"), (UTILITY, "contains", "ELECTRIC"), (UTILITY, "contains", "BROADBAND"),
    (UTILITY, "contains", "TATA PLAY"), (UTILITY, "contains", "BSNL"), (UTILITY, "regex", r"\bGAS\b"),
    (UTILITY, "regex", r"\bWATER\b"),
]

#: Everything that differs between cards, in one place. `classes` are shown in this order on
#: the dashboard; `rates` are the defaults copied onto a new card and editable per card;
#: `emi_earns` is False where EMI conversions earn nothing (true for SBI, as ten statements
#: proved, false for Amazon Pay ICICI).
PROFILES = {
    "sbi_cashback": {
        "classes": [(ONLINE, "Online"), (OFFLINE, "In person"), (EXCLUDED, "Earns nothing")],
        "rules": DEFAULT_RULES, "default": OFFLINE, "emi_earns": True,
        "rates": {ONLINE: 5, OFFLINE: 1, EXCLUDED: 0}, "cap": 5000.0,
        "statement_day": 11, "grace_days": 20, "buffer": 1, "verified": 1,
        "annual_fee": 999.0, "fee_waiver_spend": 200000.0, "credit_limit": 400000.0},
    "icici_amazon": {
        "classes": [(AMAZON, "Amazon"), (PARTNER, "Amazon Pay partners"), (OTHER, "Everywhere else"),
                    (EXCLUDED, "Earns nothing")],
        "rules": AMAZON_RULES, "default": OTHER, "emi_earns": False,
        "rates": {AMAZON: 5, PARTNER: 2, OTHER: 1, EXCLUDED: 0}, "cap": 0.0,
        "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "icici_rubyx": {
        "classes": [(INTERNATIONAL, "International"), (DOMESTIC, "Everyday spend"),
                    (UTILITY, "Utility and insurance"), (EXCLUDED, "Earns nothing (fuel)")],
        "rules": RUBYX_RULES, "default": DOMESTIC, "emi_earns": False, "point_value": POINT_VALUE,
        # percent = points per Rs 100 x value of a point: 4 x 0.25 = 1%, 2 x 0.25 = 0.5%, 1 x 0.25 = 0.25%
        "rates": {INTERNATIONAL: 1.0, DOMESTIC: 0.5, UTILITY: 0.25, EXCLUDED: 0}, "cap": 0.0,
        "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "icici_sapphiro": {
        "classes": [(INTERNATIONAL, "International"), (DOMESTIC, "Everyday spend"),
                    (UTILITY, "Utility and insurance"), (EXCLUDED, "Earns nothing (fuel)")],
        "rules": RUBYX_RULES, "default": DOMESTIC, "emi_earns": False, "point_value": POINT_VALUE,
        "rates": {INTERNATIONAL: 1.0, DOMESTIC: 0.5, UTILITY: 0.25, EXCLUDED: 0}, "cap": 0.0,
        "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "bob_eterna": {
        # BOB Eterna prints its reward points per transaction and in total, so there is nothing to estimate:
        # published terms are 15 points per Rs 100 online, travel, dining and movies and 3 elsewhere, and a
        # point is worth about Rs 0.25 (third-party pages; the statement does not say), which is the one
        # assumption and the only thing a rate edit changes. At least 1,000 points are needed to redeem.
        "classes": [(OTHER, "All spend")], "rules": [], "default": OTHER, "emi_earns": True,
        "rates": {OTHER: 0}, "cap": 0.0, "point_value": 0.25, "points_from_statement": True, "redeem_at": 1000,
        "statement_day": 0, "grace_days": 19, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "hdfc_neu": {
        # Tata Neu Infinity HDFC: the statement prints NeuCoins per line (base, 1.5%) and in total (base plus
        # bonus: an extra 3.5% on Tata brands, category bonuses), so rewards are read. 1 NeuCoin is worth Rs 1
        # on Tata Neu (that is Tata's stated value, and the one assumption). Coins move to Tata Neu by
        # themselves, so there is no minimum to redeem.
        "classes": [(OTHER, "All spend")], "rules": [], "default": OTHER, "emi_earns": True,
        "rates": {OTHER: 0}, "cap": 0.0, "point_value": 1.0, "points_from_statement": True,
        "points_unit": "NeuCoins", "redeem_at": 0,
        "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "amex_smartearn": {
        # An Amex activity download has no reward earned or balance, only the points the user spent as bill
        # credits ("Pay with Points Credit"). That is realised reward value, shown as rewards *redeemed*,
        # never as an estimate of what was earned.
        "classes": [(OTHER, "All spend")], "rules": [], "default": OTHER, "emi_earns": True,
        "rates": {OTHER: 0}, "cap": 0.0, "realised_rewards": True, "earned_label": "Rewards redeemed",
        "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
    "generic": {
        "classes": [(OTHER, "All spend")], "rules": [], "default": OTHER, "emi_earns": True,
        "rates": {OTHER: 0}, "cap": 0.0, "statement_day": 0, "grace_days": 20, "buffer": 2, "verified": 0,
        "annual_fee": 0.0, "fee_waiver_spend": 0.0, "credit_limit": 0.0},
}


def profile_of(card):
    return PROFILES.get((card or {}).get("profile") or "generic", PROFILES["generic"])


def card_rates(card):
    """The card's percent-per-class, with the profile's defaults filling any gap."""
    try:
        own = json.loads(card.get("rates") or "{}")
    except ValueError:
        own = {}
    return {**profile_of(card)["rates"], **{k: float(v) for k, v in own.items()}}


def classify(merchant, rules=None, default=OFFLINE):
    """Which reward class a merchant earns in. First matching rule wins."""
    m = merchant.upper()
    for cls, kind, pattern in (rules if rules is not None else DEFAULT_RULES):
        if kind == "contains" and pattern in m:
            return cls
        if kind == "prefix" and m.startswith(pattern):
            return cls
        if kind == "regex" and re.search(pattern, m):
            return cls
    return default  # a card-present swipe is the safe assumption on SBI


def alias(merchant):
    """Group a merchant's many statement spellings under one readable name."""
    m = merchant.upper()
    for name, keys in ALIASES:
        if any(k in m for k in keys):
            return name
    return re.sub(r"^[A-Z]{2,6}\*", "", merchant).strip().title()


def user_rules(db, card_id):
    """Saved corrections, newest first, ahead of the card's built-in rules.

    A correction applies to every number the card has had, so it survives a re-issue.
    """
    card = get_card(db, card_id) or {}
    ids = [c["id"] for c in family_of(db, card_id)] if card else [card_id]
    rows = db.execute(f"""SELECT cls, match_type, pattern FROM card_merchant_rules
                          WHERE card_id IS NULL OR card_id IN ({",".join("?" * len(ids))}) ORDER BY id DESC""",
                      ids).fetchall()
    return [(r["cls"], r["match_type"], r["pattern"].upper()) for r in rows] + profile_of(card)["rules"]


def _signed(t):
    """A row's contribution to net spend: purchases and EMI instalments add, refunds subtract."""
    if t.get("is_spend"):
        return t["amount"]
    if t.get("kind") == "refund":
        return -t["amount"]
    return 0.0


# ---------------------------------------------------------------- earn engine

def earn(txns, rules, rates=None, cap=5000.0, default=OFFLINE, emi_earns=True):
    """Cashback per row for one statement, in date order, respecting the cap.

    Order matters: once a cap is reached the rest of the cycle earns nothing, so an earlier
    purchase is worth more than a later one. A refund claws back what its purchase earned.
    A cap of 0 means uncapped. Returns the total.
    """
    rates = rates if rates is not None else PROFILES["sbi_cashback"]["rates"]
    earned = 0.0
    for t in sorted((t for t in txns if t.get("is_spend") or t.get("kind") == "refund"),
                    key=lambda t: t["tx_date"]):
        t["cls"] = classify(t["merchant"], rules, default)
        if t.get("ccy") and INTERNATIONAL in rates and t["cls"] != EXCLUDED:
            t["cls"] = INTERNATIONAL          # billed in a foreign currency
        if t.get("emi") and not emi_earns:
            t["cls"] = EXCLUDED
        pct = rates.get(t["cls"], 0) / 100
        if t.get("is_spend"):
            want = t["amount"] * pct
            give = want if cap <= 0 else min(want, max(cap - earned, 0))
            t["cashback"], t["capped"] = round(give, 2), int(give < want - 0.01)
        else:
            t["cashback"], t["capped"] = -round(t["amount"] * pct, 2), 0
        earned += t["cashback"]
    return round(earned, 2)


# ---------------------------------------------------------------- cards and statements

def get_card(db, card_id=None):
    """The card to work with. With no id, the first active card."""
    if card_id:
        row = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    else:
        row = db.execute("SELECT * FROM cards WHERE status='active' ORDER BY id LIMIT 1").fetchone()
    return dict(row) if row else None


def resolve_card(db, info):
    """The card a statement belongs to, created from the statement the first time it is seen.

    A card is its issuer plus the last digits of its number. A new one starts from its
    profile's published terms; whether its cycle is verified starts False unless the
    profile says it is known.
    """
    issuer, last4 = info.get("issuer", ""), (info.get("last4") or "")
    rows = [dict(r) for r in db.execute("SELECT * FROM cards WHERE issuer=?", (issuer,))]
    for r in rows:
        if last4 and r["last4"] and (r["last4"].endswith(last4) or last4.endswith(r["last4"])):
            return r
    if rows and not last4:
        return rows[0]
    return _insert_card(db, info)


def _insert_card(db, info):
    """A new card on its own billing account, started from its profile's published terms."""
    issuer, last4 = info.get("issuer", ""), (info.get("last4") or "")
    P = PROFILES.get(info.get("profile") or "generic", PROFILES["generic"])
    name = info.get("name") or "Credit card"
    acct = db.execute("INSERT INTO card_accounts (issuer, label) VALUES (?,?)", (issuer, name)).lastrowid
    cur = db.execute(
        """INSERT INTO cards (name, issuer, last4, profile, rates, credit_limit, statement_day, grace_days,
                              pay_buffer_days, cycle_verified, annual_fee, fee_waiver_spend, cashback_cap, account_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, issuer, last4, info.get("profile") or "generic",
         json.dumps(P["rates"]), P["credit_limit"], P["statement_day"], P["grace_days"], P["buffer"],
         P["verified"], P["annual_fee"], P["fee_waiver_spend"], P["cap"], acct))
    return get_card(db, cur.lastrowid)


# ---------------------------------------------------------------- accounts and card lineage

#: A card number that starts within this many days of another stopping, on the same bill,
#: is that card's replacement. Wide enough to span a quiet spell while the new card arrives (the
#: real data had 95 days without a purchase between two numbers of one card), narrow enough that a
#: card opened years later is not mistaken for a replacement.
REPLACE_GAP_DAYS = 120


def link_accounts(db, card_ids):
    """Put these cards on one billing account: they were listed on the same statement."""
    q = ",".join("?" * len(card_ids))
    accts = sorted({r[0] for r in db.execute(f"SELECT account_id FROM cards WHERE id IN ({q})", card_ids)})
    keep = accts[0]
    for a in accts[1:]:
        db.execute("UPDATE cards SET account_id=? WHERE account_id=?", (keep, a))
        db.execute("DELETE FROM card_accounts WHERE id=?", (a,))
    return keep


def account_cards(db, account_id):
    """Every card number on a billing account, with the dates it was actually used to spend."""
    rows = db.execute("""SELECT c.*, MIN(t.tx_date) AS _lo, MAX(t.tx_date) AS _hi FROM cards c
                         LEFT JOIN card_txns t ON t.card_id = c.id AND (t.is_spend = 1 OR t.kind = 'refund')
                         WHERE c.account_id = ? GROUP BY c.id ORDER BY _lo, c.id""", (account_id,))
    return [dict(r) for r in rows]


def lineage(cards_):
    """Group the card numbers on one account into physical cards.

    Banks re-issue a card under a new number. A number that starts within `REPLACE_GAP_DAYS`
    after another one stops, without overlapping it, is treated as its replacement. Two numbers
    used at the same time are two cards. It is computed from the dates on every read, so the
    answer does not depend on the order statements were uploaded in, and it is an inference:
    the page shows every number of a card so a wrong grouping is visible.
    """
    chains = []
    for c in sorted(cards_, key=lambda c: (c["_lo"] or "9999", c["id"])):
        best = None
        for ch in chains:
            end = ch[-1]
            if c["_lo"] and end["_hi"] and end["_hi"] <= c["_lo"]:
                gap = (date.fromisoformat(c["_lo"]) - date.fromisoformat(end["_hi"])).days
                if gap <= REPLACE_GAP_DAYS and (best is None or gap < best[0]):
                    best = (gap, ch)
        if best:
            best[1].append(c)
        else:
            chains.append([c])
    return chains


def family_of(db, card_id):
    """The card numbers that are one physical card, oldest first."""
    card = get_card(db, card_id)
    for chain in lineage(account_cards(db, card["account_id"])):
        if any(c["id"] == card_id for c in chain):
            return chain
    return [card]


#: Colours handed out to cards, in order, the most mutually distinct first. A card keeps the colour it has; one
#: you choose in Admin is yours. Beyond the palette a new hue is generated, so no two cards ever share one.
PALETTE = ["#7c74ff", "#f5b942", "#38bdf8", "#f472b6", "#3ecf8e", "#fb7c4a", "#e2e8f0", "#a3e635", "#c084fc", "#2dd4bf", "#f87171"]
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _generated(n):
    """The n-th extra colour: hues a golden angle apart, so they stay spread out however many there are."""
    import colorsys
    r, g, b = colorsys.hls_to_rgb(((n * 137.508) % 360) / 360, 0.62, 0.7)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _assign_colors(cards_):
    """Give each card a colour: its own if it was chosen, otherwise the first one nobody else holds."""
    taken = {c["color"].lower() for c in cards_ if c.get("color")}
    spare = (p for p in (list(PALETTE) + [_generated(i) for i in range(1, 200)]) if p.lower() not in taken)
    for c in sorted(cards_, key=lambda c: c["id"]):
        if not c.get("color"):
            c["color"] = next(spare)


def list_cards(db):
    """One entry per physical card (its newest number), most recently used first."""
    out = []
    for (acct,) in db.execute("SELECT id FROM card_accounts ORDER BY id").fetchall():
        for chain in lineage(account_cards(db, acct)):
            rep = chain[-1]
            out.append({**{k: v for k, v in rep.items() if not k.startswith("_")},
                        "numbers": [c["last4"] for c in chain], "members": [c["id"] for c in chain],
                        "last_used": rep["_hi"] or ""})
    chosen = {id(c): bool(c.get("color")) for c in out}
    _assign_colors(out)
    for c in out:                 # a colour handed out is kept, so it never moves when other cards change
        if not chosen[id(c)]:
            for i in c["members"]:
                db.execute("UPDATE cards SET color=? WHERE id=? AND color=''", (c["color"], i))
    db.commit()
    by_use = sorted(out, key=lambda c: c["last_used"], reverse=True)
    # Cards you have placed come first in the order you chose, closed ones included; the rest stay most recently used first.
    return sorted(by_use, key=lambda c: (not c.get("sort_order"), c.get("sort_order") or 0))


def set_card_order(db, ids):
    """Remember the order cards were dragged into. `ids` are card ids as listed; every number of a card moves with it."""
    known = {c["id"]: c for c in list_cards(db)}
    bad = [i for i in ids if i not in known]
    if bad:
        raise KeyError(bad[0])
    for pos, cid in enumerate(ids, start=1):
        for m in known[cid]["members"]:
            db.execute("UPDATE cards SET sort_order=? WHERE id=?", (pos, m))
    db.commit()
    return [c["id"] for c in list_cards(db)]


def _row_hash(card_id, t, occurrence=0):
    """Identity of a transaction, so re-importing an overlapping statement adds nothing.

    Two genuinely identical lines on one day (two Rs 40 canteen purchases) are different
    transactions, so the n-th repeat gets its own hash. The first keeps the plain key, which
    is what earlier imports stored, so re-importing never duplicates what is already there.
    """
    import hashlib
    key = f"{card_id}|{t['tx_date']}|{t['amount']:.2f}|{t['dc']}|{t['detail'].upper()}"
    if t.get("ref"):
        key += f"|{t['ref']}"
    if occurrence:
        key += f"#{occurrence}"
    return hashlib.sha1(key.encode()).hexdigest()


def _learn_cycle(db, card, parsed):
    """Take the billing cycle from a statement that states it.

    SBI, BOB and HDFC print a statement date and a due date, so the cycle is read, not assumed, and the
    card becomes verified. ICICI's yearly file prints neither; the statement day can only be inferred from
    when EMI instalments post, so that case stays unverified.

    Order must not matter. A statement older than the newest one we hold is normally ignored (the newest
    states the current cycle), but not while the cycle is still unverified: the newest statement may owe
    nothing and print no due date (HDFC prints "Nil"), and an older one that does print it must still be used.
    """
    newest = db.execute("SELECT MAX(period_to) FROM card_statements WHERE card_id=?", (card["id"],)).fetchone()[0]
    older = bool(newest and parsed["period_to"] < newest)
    if parsed.get("due_date") and parsed.get("stmt_date") and (not older or not card.get("cycle_verified")):
        s, d = date.fromisoformat(parsed["stmt_date"]), date.fromisoformat(parsed["due_date"])
        if 0 < (d - s).days <= 60:
            db.execute("UPDATE cards SET statement_day=?, grace_days=?, cycle_verified=1 WHERE id=?",
                       (s.day, (d - s).days, card["id"]))
            if not older and parsed.get("credit_limit", 0) > 0:
                db.execute("UPDATE cards SET credit_limit=? WHERE id=?", (parsed["credit_limit"], card["id"]))
            return
    if older:
        return
    if parsed.get("credit_limit", 0) > 0 and card.get("credit_limit", 0) != parsed["credit_limit"]:
        db.execute("UPDATE cards SET credit_limit=? WHERE id=?", (parsed["credit_limit"], card["id"]))
    hint = parsed.get("statement_day_hint")
    if hint and not card.get("cycle_verified"):
        db.execute("UPDATE cards SET statement_day=? WHERE id=?", (hint, card["id"]))
    elif parsed.get("kind") == "cycle" and parsed.get("stmt_date") and not card.get("cycle_verified"):
        db.execute("UPDATE cards SET statement_day=? WHERE id=?",          # no due date printed: the day is still known
                   (date.fromisoformat(parsed["stmt_date"]).day, card["id"]))


def save_statement(db, card, parsed, filename):
    """Store one parsed statement and its transactions. Returns (statement_id, rows added)."""
    cid = card["id"]
    _learn_cycle(db, card, parsed)
    rules, P = user_rules(db, cid), profile_of(card)
    calc = earn(parsed["txns"], rules, card_rates(card), card.get("cashback_cap") or 0,
                P["default"], P["emi_earns"])

    db.execute("""INSERT INTO card_statements
          (card_id, kind, period_from, period_to, stmt_date, due_date, total_due, min_due,
           purchases, credits, fees, available_credit, cashback_reported, cashback_calc, file,
           points_earned, points_balance)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(card_id, period_to) DO UPDATE SET
            kind=excluded.kind, period_from=excluded.period_from, stmt_date=excluded.stmt_date,
            due_date=excluded.due_date, total_due=excluded.total_due, min_due=excluded.min_due,
            purchases=excluded.purchases, credits=excluded.credits, fees=excluded.fees,
            available_credit=excluded.available_credit,
            cashback_reported=excluded.cashback_reported,
            cashback_calc=excluded.cashback_calc, file=excluded.file,
            points_earned=excluded.points_earned, points_balance=excluded.points_balance""",
               (cid, parsed.get("kind", "cycle"), parsed["period_from"], parsed["period_to"],
                parsed["stmt_date"], parsed["due_date"], parsed["total_due"], parsed["min_due"],
                parsed["purchases"], parsed["credits"], parsed["fees"], parsed["available_credit"],
                parsed["cashback_reported"], calc, filename,
                parsed.get("points_earned"), parsed.get("points_balance")))
    sid = db.execute("SELECT id FROM card_statements WHERE card_id=? AND period_to=?",
                     (cid, parsed["period_to"])).fetchone()[0]

    added, seen = 0, {}
    for t in parsed["txns"]:
        base = _row_hash(cid, t)
        n = seen[base] = seen.get(base, -1) + 1
        cur = db.execute("""INSERT OR IGNORE INTO card_txns
              (card_id, statement_id, row_hash, tx_date, detail, merchant, city, amount,
               dc, emi, is_spend, kind, ref, cls, cashback, capped, ccy, points, category)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (cid, sid, _row_hash(cid, t, n), t["tx_date"], t["detail"], t["merchant"],
                          t["city"], t["amount"], t["dc"], t["emi"], t["is_spend"], t.get("kind", ""),
                          t.get("ref", ""), t.get("cls", ""), t.get("cashback", 0), t.get("capped", 0),
                          t.get("ccy", ""), t.get("points", 0), t.get("category", "")))
        added += cur.rowcount
        if not cur.rowcount and t.get("ccy"):   # already stored, before the currency was kept
            db.execute("UPDATE card_txns SET ccy=? WHERE row_hash=?", (t["ccy"], _row_hash(cid, t, n)))
    return sid, added


def import_pdf(db, card_id, name, source, password="", allow_llm=False):
    """Read, parse, validate and store one statement file. Never raises: returns a report row.

    A file can cover several cards (an ICICI account lists each card number), and each card is
    taken from the statement itself and created if it is new, so statements from different
    cards can be uploaded together. Cards listed on one statement share a bill, so they are put
    on one billing account. `card_id` forces a single card, mainly for scripts. `source` is a path
    or file-like object. A failure leaves the database untouched.
    """
    try:
        parsed_list, parser = parse_any(read_pdf(source, password, name), allow_llm)
        saved = []
        for parsed in parsed_list:
            card = get_card(db, card_id) if card_id else resolve_card(db, parsed["card"])
            _sid, added = save_statement(db, card, parsed, name)
            saved.append((card, parsed, added))
        ids = sorted({c["id"] for c, _, _ in saved})
        if len(ids) > 1:
            link_accounts(db, ids)
        db.commit()
        parts = [{"card": c["name"], "card_id": c["id"], "period_to": p["period_to"], "spend": p["purchases"],
                  "rows": len(p["txns"]), "added": a} for c, p, a in saved]
        first = saved[0][1]
        return {"file": name, "ok": True, "parser": parser, "cards": parts,
                "card": ", ".join(dict.fromkeys(x["card"] for x in parts)), "card_id": parts[0]["card_id"],
                "period_to": first["period_to"], "spend": round(sum(x["spend"] for x in parts), 2),
                "rows": sum(x["rows"] for x in parts), "added": sum(x["added"] for x in parts),
                "skipped": sum(x["rows"] - x["added"] for x in parts),
                "cashback": first["cashback_reported"], "kind": first.get("kind", "cycle")}
    except Exception as e:  # one bad file must not stop the rest
        db.rollback()
        return {"file": name, "ok": False, "error": str(e)}


def import_files(db, card_id, files, password="", allow_llm=False):
    """Import several uploaded statements: `files` is a list of (name, file-like)."""
    report = [import_pdf(db, card_id, name, src, password, allow_llm) for name, src in files]
    for cid in {x["card_id"] for r in report if r["ok"] for x in r["cards"]}:
        reclassify(db, cid)
    return report


def reclassify(db, card_id):
    """Re-apply the rules to every stored transaction of this card number."""
    card = get_card(db, card_id) or {}
    rules, P, rates = user_rules(db, card_id), profile_of(card), card_rates(card)
    for sid, in db.execute("SELECT id FROM card_statements WHERE card_id=? ORDER BY period_to",
                           (card_id,)).fetchall():
        rows = [dict(r) for r in db.execute("SELECT * FROM card_txns WHERE statement_id=?", (sid,)).fetchall()]
        total = earn(rows, rules, rates, card.get("cashback_cap") or 0, P["default"], P["emi_earns"])
        for t in rows:
            if t["is_spend"] or t["kind"] == "refund":
                db.execute("UPDATE card_txns SET cls=?, cashback=?, capped=? WHERE id=?",
                           (t["cls"], t["cashback"], t["capped"], t["id"]))
        db.execute("UPDATE card_statements SET cashback_calc=? WHERE id=?", (total, sid))
    db.commit()


def reclassify_card(db, card_id):
    """Reclassify every number a physical card has had (a rule or a rate applies to all of them)."""
    for c in family_of(db, card_id):
        reclassify(db, c["id"])


# ---------------------------------------------------------------- administering cards

PROFILE_LABELS = {"sbi_cashback": "SBI Cashback", "icici_amazon": "Amazon Pay ICICI", "icici_rubyx": "ICICI Rubyx",
                  "icici_sapphiro": "ICICI Sapphiro", "bob_eterna": "BOB Eterna", "hdfc_neu": "HDFC Tata Neu",
                  "amex_smartearn": "Amex SmartEarn", "generic": "Usage only"}
STATUSES = ("active", "closed")


def admin_list(db):
    """Every physical card with what an admin needs to recognise it: name, numbers, scheme, status, and how
    much data it holds. Closed cards are included, listed after the active ones. Nothing here deletes."""
    out = []
    for c in list_cards(db):
        q = ",".join("?" * len(c["members"]))
        lo, hi, n, spend = db.execute(
            f"""SELECT MIN(tx_date), MAX(tx_date), COUNT(*),
                       COALESCE(SUM(CASE WHEN is_spend=1 THEN amount WHEN kind='refund' THEN -amount ELSE 0 END), 0)
                FROM card_txns WHERE card_id IN ({q}) AND (is_spend=1 OR kind='refund')""", c["members"]).fetchone()
        stmts = db.execute(f"SELECT COUNT(*) FROM card_statements WHERE card_id IN ({q})", c["members"]).fetchone()[0]
        shared = [x["name"] for x in list_cards(db) if x["account_id"] == c["account_id"] and x["id"] != c["id"]]
        out.append({"id": c["id"], "color": c["color"], "name": c["name"], "issuer": c["issuer"], "numbers": c["numbers"], "members": c["members"],
                    "profile": c["profile"], "scheme": PROFILE_LABELS.get(c["profile"], c["profile"]),
                    "network": c["network"] or "", "notes": c["notes"] or "", "credit_limit": c["credit_limit"] or 0,
                    "annual_fee": c["annual_fee"] or 0, "fee_waiver_spend": c["fee_waiver_spend"] or 0,
                    "statement_day": c["statement_day"] or 0, "grace_days": c["grace_days"] or 0, "cycle_verified": bool(c["cycle_verified"]),
                    "status": c["status"] or "active", "since": lo, "last_used": hi, "spend": round(spend, 2),
                    "transactions": n, "statements": stmts, "shared_with": shared})
    return sorted(out, key=lambda x: (x["status"] == "closed", -(int(x["last_used"].replace("-", "")) if x["last_used"] else 0)))


#: The issuer name each scheme's statements carry, so a card added by hand is the one a later import finds.
PROFILE_ISSUERS = {"sbi_cashback": "SBI Card", "icici_amazon": "ICICI Bank", "icici_rubyx": "ICICI Bank", "icici_sapphiro": "ICICI Bank",
                   "bob_eterna": "Bank of Baroda", "hdfc_neu": "HDFC Bank", "amex_smartearn": "American Express"}


def create_card(db, name, profile="generic", last4="", issuer=""):
    """Add a card by hand. It shows up at once, with no data yet, and a statement import for the same
    issuer and last digits attaches to it instead of making a second card."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name or len(name) > 60:
        raise ValueError("A card needs a name of 1 to 60 characters")
    if profile not in PROFILES:
        raise ValueError("Unknown card scheme")
    last4 = re.sub(r"\D", "", last4 or "")
    if last4 and not 4 <= len(last4) <= 5:
        raise ValueError("Enter the last 4 digits of the card number (5 for American Express)")
    issuer = PROFILE_ISSUERS.get(profile) or re.sub(r"\s+", " ", issuer or "").strip() or "Other"
    for r in db.execute("SELECT name, last4 FROM cards WHERE issuer=?", (issuer,)):
        if last4 and r["last4"] and (r["last4"].endswith(last4) or last4.endswith(r["last4"])):
            raise ValueError(f"{issuer} ···{last4} is already here as {r['name']}")
    card = _insert_card(db, {"issuer": issuer, "last4": last4, "name": name, "profile": profile})
    db.commit()
    return next(x for x in admin_list(db) if card["id"] in x["members"])


#: Numeric details an admin may change, and the range each must fall in.
_RANGES = {"credit_limit": (0, 1e8), "annual_fee": (0, 1e6), "fee_waiver_spend": (0, 1e8), "statement_day": (1, 31), "grace_days": (1, 60)}


def update_card(db, card_id, name=None, status=None, **meta):
    """Change a card's details: name, status, bank, last digits, network, notes, limit, fees, reward scheme, cycle.

    Everything is checked before anything is written, so a bad value changes nothing. Name, bank, digits, network and
    notes belong to the card as shown (its newest number). Status, scheme, limit and fees apply to every number the
    card has had, since they are one physical card; the billing cycle applies to every card on its bill. Changing the
    scheme resets the reward rates to the new scheme's and re-reads the card's transactions under them. Saving the
    cycle marks it verified, as the card's own edit dialog does. A closed card is kept in full. Nothing is deleted.
    """
    card = get_card(db, card_id)
    if not card:
        raise KeyError("card")
    meta = {k: v for k, v in meta.items() if v is not None}
    if name is not None:
        name = re.sub(r"\s+", " ", name).strip()
        if not name or len(name) > 60:
            raise ValueError("A card needs a name of 1 to 60 characters")
    if status is not None and status not in STATUSES:
        raise ValueError("Status must be active or closed")
    for k, (lo, hi) in _RANGES.items():
        if k in meta and not lo <= meta[k] <= hi:
            raise ValueError(f"{k.replace('_', ' ').capitalize()} must be between {lo:g} and {hi:g}")
    issuer = re.sub(r"\s+", " ", meta["issuer"]).strip() if "issuer" in meta else card["issuer"]
    last4 = re.sub(r"\D", "", meta["last4"]) if "last4" in meta else card["last4"]
    if not issuer:
        raise ValueError("A card needs a bank")
    if last4 != card["last4"] and last4 and not 4 <= len(last4) <= 5:     # an older card may hold fewer digits; only a change is checked
        raise ValueError("Enter the last 4 digits of the card number (5 for American Express)")
    if ("issuer" in meta or "last4" in meta) and last4:
        for r in db.execute("SELECT name, last4 FROM cards WHERE issuer=? AND id!=?", (issuer, card_id)):
            if r["last4"] and (r["last4"].endswith(last4) or last4.endswith(r["last4"])):
                raise ValueError(f"{issuer} ···{last4} is already {r['name']}")
    profile = meta.get("profile", card["profile"])
    if profile not in PROFILES:
        raise ValueError("Unknown card scheme")
    color = meta.get("color")
    if color is not None:
        color = color.strip().lower()
        if color and not _HEX.match(color):
            raise ValueError("A colour is six hex digits, like #3ecf8e")
        mine = {c["id"] for c in family_of(db, card_id)}
        for other in list_cards(db):
            if color and other["color"].lower() == color and not mine & set(other["members"]):
                raise ValueError(f"{other['name']} already uses that colour. Each card needs its own.")
    network = re.sub(r"\s+", " ", meta.get("network", card["network"]) or "").strip()[:30]
    notes = (meta.get("notes", card["notes"]) or "").strip()[:500]

    fam = [c["id"] for c in family_of(db, card_id)]
    if name is not None:
        db.execute("UPDATE cards SET name=? WHERE id=?", (name, card_id))
    db.execute("UPDATE cards SET issuer=?, last4=?, network=?, notes=? WHERE id=?", (issuer, last4, network, notes, card_id))
    if status is not None:
        for i in fam:
            db.execute("UPDATE cards SET status=? WHERE id=?", (status, i))
    for k in ("credit_limit", "annual_fee", "fee_waiver_spend"):
        if k in meta:
            for i in fam:
                db.execute(f"UPDATE cards SET {k}=? WHERE id=?", (meta[k], i))
    if color is not None:
        for i in fam:
            db.execute("UPDATE cards SET color=? WHERE id=?", (color, i))
    rescheme = profile != card["profile"]
    if rescheme:
        for i in fam:
            db.execute("UPDATE cards SET profile=?, rates=? WHERE id=?", (profile, json.dumps(PROFILES[profile]["rates"]), i))
    if "statement_day" in meta or "grace_days" in meta:
        sd, gd = meta.get("statement_day", card["statement_day"]), meta.get("grace_days", card["grace_days"])
        for c in account_cards(db, card["account_id"]):                  # one bill, one cycle
            db.execute("UPDATE cards SET statement_day=?, grace_days=?, cycle_verified=1 WHERE id=?", (sd, gd, c["id"]))
    db.commit()
    if rescheme:
        reclassify_card(db, card_id)
    return next(x for x in admin_list(db) if card_id in x["members"])


# ---------------------------------------------------------------- scheme benefits

REDEMPTION_FEE, GST = 99.0, 0.18

#: What an ICICI premium card gives beyond points, from the bank's own pages (icici.bank.in). Where the
#: page is silent the terms say so rather than guess: the value of a point, exclusions beyond fuel, and
#: whether a year means April-March or the card anniversary are not published there.
#:   milestone = (spend that earns the first bonus, points for it, points per further Rs 1 lakh, yearly cap)
#:   lounge    = domestic visits per quarter once a quarter's spend passes `threshold`; `lag` is 1 when the
#:               previous quarter's spend counts (Rubyx) and 0 when the same quarter's does (Sapphiro)
RUBYX_TERMS = {"kind": "rubyx", "name": "Rubyx", "milestone": (300_000, 3000, 1500, 15_000),
               "lounge": {"threshold": 75_000, "visits": 2, "lag": 1, "extra": "8 railway lounge visits a year"}}
SAPPHIRO_TERMS = {"kind": "sapphiro", "name": "Sapphiro", "milestone": (400_000, 4000, 2000, 20_000),
                  "lounge": {"threshold": 75_000, "visits": 4, "lag": 0,
                             "extra": "2 international lounge visits a year (Priority Pass)"}}
TERMS = {"icici_rubyx": RUBYX_TERMS, "icici_sapphiro": SAPPHIRO_TERMS}
# Kept as module constants because the Rubyx numbers are used directly in tests and docs.
MILESTONE_AT, MILESTONE_BASE, MILESTONE_STEP, MILESTONE_CAP = RUBYX_TERMS["milestone"]
LOUNGE_SPEND, LOUNGE_VISITS = 75_000, 2


def milestone_points(spend, terms=RUBYX_TERMS):
    """Bonus points for a year's spend, e.g. Rubyx: 3,000 at Rs 3 lakh, 1,500 more per further lakh, up to 15,000."""
    at, base, step, cap = terms["milestone"]
    if spend < at:
        return 0
    return min(base + step * int((spend - at) // 100_000), cap)


def _quarter(d):
    return f"{d.year} Q{(d.month - 1) // 3 + 1}"


def _prev_quarter(q):
    year, n = int(q[:4]), int(q[-1])
    return f"{year - 1} Q4" if n == 1 else f"{year} Q{n - 1}"


def card_benefits(live, fee_rows, today, point_value, terms=RUBYX_TERMS):
    """The yearly milestone, lounge access and redemption cost of a scheme with published terms.

    `live` are spend rows (with `net`, `cls`, `_d`, `merchant`); fuel and other excluded spend does
    not count towards a milestone or a lounge quarter. The bank may count the year from the card's
    anniversary rather than April, which the statements do not show, so years here are financial
    years and are labelled as such.
    """
    at, base, step, cap = terms["milestone"]
    lounge = terms["lounge"]
    elig = [r for r in live if r["cls"] != EXCLUDED]
    by_fy, by_q, swipes = {}, {}, {}
    for r in elig:
        by_fy[_fy(r["_d"])] = by_fy.get(_fy(r["_d"]), 0.0) + r["net"]
        by_q[_quarter(r["_d"])] = by_q.get(_quarter(r["_d"]), 0.0) + r["net"]
    for r in live:
        if "DREAMFOLKS" in r["merchant"].upper():          # the Rs 2 lounge-entry authorisation
            swipes[_quarter(r["_d"])] = swipes.get(_quarter(r["_d"]), 0) + 1
    pts = lambda v: milestone_points(v, terms)
    years = [{"fy": fy, "spend": round(v, 2), "points": pts(v), "value": round(pts(v) * point_value, 2)}
             for fy, v in sorted(by_fy.items(), reverse=True)]
    cur = by_fy.get(_fy(today), 0.0)
    nxt = at if cur < at else at + 100_000 * (int((cur - at) // 100_000) + 1)
    over = lambda q: by_q.get(q, 0.0) > lounge["threshold"] if lounge["lag"] else by_q.get(q, 0.0) >= lounge["threshold"]
    quarters = [{"quarter": q, "spend": round(v, 2), "earns_next": bool(lounge["lag"]) and over(q),
                 "entitled": over(_prev_quarter(q)) if lounge["lag"] else over(q), "swipes": swipes.get(q, 0)}
                for q, v in sorted(by_q.items(), reverse=True)[:6]]
    redemptions = [r for r in fee_rows if "REWARD REDEMPTION" in r["detail"].upper()]
    return {
        "kind": terms["kind"], "name": terms["name"], "point_value": point_value,
        "milestone": {"threshold": at, "base": base, "step": step, "cap": cap, "years": years,
                      "current": {"fy": _fy(today), "spend": round(cur, 2), "points": pts(cur),
                                  "next_at": nxt, "to_go": round(max(nxt - cur, 0), 2), "next_points": pts(nxt)}},
        "lounge": {"threshold": lounge["threshold"], "visits": lounge["visits"], "lag": lounge["lag"],
                   "extra": lounge["extra"], "quarters": quarters},
        "redemptions": {"count": len(redemptions),
                        "cost": round(sum(r["amount"] for r in redemptions) * (1 + GST), 2),
                        "per_redemption": round(REDEMPTION_FEE * (1 + GST), 2)},
    }


def rubyx_benefits(live, fee_rows, today, point_value):
    return card_benefits(live, fee_rows, today, point_value, RUBYX_TERMS)


# ---------------------------------------------------------------- dashboard

def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def _fy(d):
    y = d.year if d.month >= 4 else d.year - 1
    return f"FY{y}"


def _segments(stmts, sday):
    """Split monthly statements into unbroken runs, and list the statements that are missing between them.

    Returns (runs, run_of_statement_id, missing_period_end_dates). Statement periods are contiguous, so a
    period that does not start the day after the previous one ended means a statement is missing.
    """
    runs, seg_of, missing = [], {}, []
    for st in stmts:
        start, end = date.fromisoformat(st["period_from"]), date.fromisoformat(st["period_to"])
        if runs and (start - runs[-1][1]).days > 7:                # a gap of more than a week
            probe = runs[-1][1]
            while sday:                                             # estimate which statements fell in the gap
                probe = cf.statement_on_or_after(probe + timedelta(days=1), sday)
                if probe >= start:
                    break
                missing.append(probe.isoformat())
            runs.append([start, end])
        elif runs:
            runs[-1][1] = end
        else:
            runs.append([start, end])
        seg_of[st["id"]] = len(runs) - 1
    return runs, seg_of, missing


def dashboard(db, card_id=None, today=None):
    """Everything the Cards page shows for one card, in one payload."""
    today = today or date.today()
    card = get_card(db, card_id)
    if not card:
        return {"card": None}
    # A card is every number it has had; a bill is shared by every card on the account.
    fam = family_of(db, card["id"])
    card = get_card(db, fam[-1]["id"])                    # the newest number stands for the card
    ids = [c["id"] for c in fam]
    acct = account_cards(db, card["account_id"])
    base = max(acct, key=lambda c: c["_hi"] or "")        # the account's newest card owns the billing cycle
    cid, P, rates = card["id"], profile_of(card), card_rates(card)
    sday, grace = base["statement_day"] or 0, base["grace_days"] or 20
    q = ",".join("?" * len(ids))
    # Rows stored before reward classes covered refunds have no class yet: classify them once.
    if db.execute(f"""SELECT 1 FROM card_txns WHERE card_id IN ({q}) AND cls='' AND (is_spend=1 OR kind='refund')
                      LIMIT 1""", ids).fetchone():
        for i in ids:
            reclassify(db, i)

    stmts = [dict(r) for r in db.execute(
        f"SELECT * FROM card_statements WHERE card_id IN ({q}) ORDER BY period_to", ids).fetchall()]
    rows = [dict(r) for r in db.execute(
        f"SELECT * FROM card_txns WHERE card_id IN ({q}) ORDER BY tx_date, id", ids).fetchall()]
    billed_on = {s["id"]: date.fromisoformat(s["period_to"]) for s in stmts if s["kind"] == "cycle"}
    for r in rows:
        r["_d"] = date.fromisoformat(r["tx_date"])
        r["_stmt"] = billed_on.get(r["statement_id"])      # None where no statement states the cycle
        r["net"] = _signed(r)
    live = [r for r in rows if r["net"]]                       # rows that count towards spend
    spend_rows = [r for r in rows if r["is_spend"]]

    gross = sum(r["amount"] for r in spend_rows)
    refunds = sum(r["amount"] for r in rows if r["kind"] == "refund")
    net = gross - refunds
    reported = [s["cashback_reported"] for s in stmts if s["cashback_reported"] is not None]
    est = sum(r["cashback"] for r in live)
    earned = float(sum(reported)) if reported else est         # what the statements paid, else our estimate
    # Some statements print reward POINTS (BOB Eterna): those are read, not estimated. The rupee value of a
    # point is the one assumption, and it is shown.
    pts_stmts = [s for s in stmts if s["points_earned"] is not None]
    points_total = sum(s["points_earned"] for s in pts_stmts)
    if P.get("points_from_statement") and pts_stmts:
        earned = points_total * P["point_value"]
        reported = [earned]
    # Rewards the user spent as bill credits (Amex "Pay with Points"): realised value, not what was earned.
    realised = sum(r["amount"] for r in rows if r["kind"] == "cashback")
    if P.get("realised_rewards") and realised:
        earned = realised
        reported = [earned]
    # A scheme with a yearly milestone (Rubyx) pays bonus points on top of the per-spend rewards: real value.
    benefits = (card_benefits(live, [r for r in rows if r["kind"] == "fee"], today, P["point_value"], TERMS[card["profile"]])
                if card["profile"] in TERMS else None)
    bonus = sum(y["value"] for y in benefits["milestone"]["years"]) if benefits else 0.0
    earned += bonus
    fees = sum(s["fees"] or 0 for s in stmts)

    # By reward class, using the profile's order. Refunds are netted into their class.
    by_class = {}
    for c, _label in P["classes"]:
        cr = [r for r in live if r["cls"] == c]
        amt = sum(r["net"] for r in cr)
        by_class[c] = {"spend": round(amt, 2), "count": sum(1 for r in cr if r["is_spend"]),
                       "pct": _pct(amt, net), "cashback": round(sum(r["cashback"] for r in cr), 2)}
        if P.get("point_value"):
            by_class[c]["points"] = round(by_class[c]["cashback"] / P["point_value"])

    # Per merchant, grouped by alias: where the money and the cashback actually go.
    merch = {}
    for r in live:
        a = alias(r["merchant"])
        m = merch.setdefault(a, {"name": a, "spend": 0.0, "count": 0, "cashback": 0.0, "cls": r["cls"], "emi": 0})
        m["spend"] += r["net"]
        m["cashback"] += r["cashback"]
        m["count"] += int(bool(r["is_spend"]))
        m["emi"] += int(r["emi"] or 0) if r["is_spend"] else 0
        if m["cls"] != r["cls"]:
            m["cls"] = "mixed"
    merchants = sorted((m for m in merch.values() if m["spend"] > 0), key=lambda m: -m["spend"])
    for m in merchants:
        m["spend"], m["cashback"] = round(m["spend"], 2), round(m["cashback"], 2)
        m["rate"] = _pct(m["cashback"], m["spend"])

    # The issuer's own spend categories, where it gives them (Amex does, no other card here does).
    by_cat = {}
    for r in live:
        if (r.get("category") or "").strip():
            e = by_cat.setdefault(r["category"].strip(), {"name": r["category"].strip(), "spend": 0.0, "count": 0})
            e["spend"] += r["net"]
            e["count"] += int(bool(r["is_spend"]))
    cat_total = sum(e["spend"] for e in by_cat.values() if e["spend"] > 0)
    categories = sorted(({**e, "spend": round(e["spend"], 2), "pct": _pct(e["spend"], cat_total)}
                         for e in by_cat.values() if e["spend"] > 0), key=lambda e: -e["spend"])

    # Leakage only makes sense where there is an online / in-person split to move between.
    leaks = []
    if ONLINE in rates and OFFLINE in rates:
        gap = rates[ONLINE] - rates[OFFLINE]
        leaks = sorted(({"name": m["name"], "spend": m["spend"], "cls": m["cls"],
                         "missed": round(m["spend"] * (gap if m["cls"] == OFFLINE else rates[ONLINE]) / 100, 2)}
                        for m in merchants if m["cls"] in (OFFLINE, EXCLUDED)), key=lambda l: -l["missed"])[:8]

    # Cycles: by the statement date where the cycle is known, else by calendar month.
    def cycle_of(d):
        if sday:
            return cf.statement_on_or_after(d, sday)
        return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])  # no cycle known: calendar month

    cyc = {}
    for r in live:
        key = r["_stmt"] or cycle_of(r["_d"])
        c = cyc.setdefault(key, {"spend": 0.0, "est": 0.0, "real": 0.0})
        c["spend"] += r["net"]
        c["est"] += r["cashback"]
    if P.get("realised_rewards"):
        for r in rows:
            if r["kind"] == "cashback":
                cyc.setdefault(r["_stmt"] or cycle_of(r["_d"]), {"spend": 0.0, "est": 0.0, "real": 0.0})["real"] += r["amount"]
    paid_by_stmt = {s["period_to"]: s for s in stmts if s["kind"] == "cycle"}
    months = []
    for key in sorted(cyc)[-12:]:
        c, st = cyc[key], paid_by_stmt.get(key.isoformat())
        c.setdefault("real", 0.0)
        got = st["cashback_reported"] if st and st["cashback_reported"] is not None else None
        if got is None and st and st["points_earned"] is not None and P.get("points_from_statement"):
            got = round(st["points_earned"] * P["point_value"], 2)          # points printed on that statement
        if got is None and P.get("realised_rewards"):
            got = round(c["real"], 2)
        months.append({"period_to": key.isoformat(), "spend": round(c["spend"], 2),
                       "cashback": got if got is not None else round(c["est"], 2),
                       "reported": got is not None, "calc": round(c["est"], 2),
                       "rate": _pct(got if got is not None else c["est"], c["spend"]),
                       "due": st["total_due"] if st else None, "fees": st["fees"] if st else None,
                       "due_date": st["due_date"] if st else None})

    # Financial years: the natural unit when statements arrive yearly.
    fys = {}
    for r in live:
        f = fys.setdefault(_fy(r["_d"]), {"fy": _fy(r["_d"]), "spend": 0.0, "cashback": 0.0, "fees": 0.0})
        f["spend"] += r["net"]
        f["cashback"] += r["cashback"]
    for r in rows:
        if r["kind"] == "fee":
            f = fys.setdefault(_fy(r["_d"]), {"fy": _fy(r["_d"]), "spend": 0.0, "cashback": 0.0, "fees": 0.0})
            f["fees"] += r["amount"] if r["dc"] == "D" else -r["amount"]
        elif P.get("realised_rewards") and r["kind"] == "cashback":
            f = fys.setdefault(_fy(r["_d"]), {"fy": _fy(r["_d"]), "spend": 0.0, "cashback": 0.0, "fees": 0.0})
            f["cashback"] += r["amount"]
    years = [{**f, "spend": round(f["spend"], 2), "cashback": round(f["cashback"], 2), "fees": round(f["fees"], 2)}
             for f in sorted(fys.values(), key=lambda f: f["fy"], reverse=True)]

    # When to pay: how the bills have been paid, and the next dates.
    year_ago = today.replace(year=today.year - 1, day=min(today.day, 28)).isoformat()
    year_spend = round(sum(r["net"] for r in live if r["tx_date"] >= year_ago), 2)
    latest = next((s for s in reversed(stmts) if s["kind"] == "cycle"), None)
    # Payments settle the whole bill, not one card, so the pay-timing maths takes every card on the account.
    aq = ",".join("?" * len(acct))
    aids = [c["id"] for c in acct]
    arows = [dict(r) for r in db.execute(
        f"SELECT tx_date, amount, dc, kind, statement_id FROM card_txns WHERE card_id IN ({aq}) ORDER BY tx_date, id", aids)]
    a_stmts = [dict(r) for r in db.execute(
        f"SELECT id, period_from, period_to FROM card_statements WHERE kind='cycle' AND card_id IN ({aq}) ORDER BY period_to", aids)]
    a_billed = {r["id"]: date.fromisoformat(r["period_to"]) for r in a_stmts}
    segments, seg_of, missing = _segments(a_stmts, sday)
    through = date.fromisoformat(arows[-1]["tx_date"]) if arows else None
    sharing = [ch[-1]["name"] for ch in lineage(acct) if cid not in [c["id"] for c in ch]]
    pay = {"statement_day": sday, "grace_days": grace, "buffer": base["pay_buffer_days"] or 1,
           "rate": base["float_rate"], "verified": bool(base["cycle_verified"]),
           "needs_cycle": not sday, "data_through": through.isoformat() if through else None,
           "stale": bool(through and (today - through).days > 45), "shared_with": sharing, "missing_statements": missing}
    if sday and arows:
        # A missing statement hides the payments made in its cycle, so a bill from before the gap would be
        # matched to a payment made weeks later and look late. Each unbroken run of statements is therefore
        # matched on its own, and whatever was still owing when a run ended is left unmatched.
        pairs, owing = [], 0.0
        for k in range(max(len(segments), 1)):
            rows_k = [r for r in arows if seg_of.get(r["statement_id"], 0) == k]
            ch = [(date.fromisoformat(r["tx_date"]), r["amount"], a_billed.get(r["statement_id"]))
                  for r in rows_k if r["dc"] == "D"]
            cr = [(date.fromisoformat(r["tx_date"]), r["amount"], r["kind"] != "payment")
                  for r in rows_k if r["dc"] == "C"]
            p_k, owing = cf.pair_payments(ch, cr)
            pairs += p_k
        h = cf.habit(pairs, sday, grace, pay["buffer"], base["float_rate"])
        recent = [c["billed"] for c in h["cycles"][1:4]] or [c["billed"] for c in h["cycles"][:1]]
        expected = sum(recent) / len(recent) if recent else 0.0
        pay.update({"habit": h, "expected_bill": round(expected, 2), "outstanding": owing,
                    "upcoming": cf.upcoming(today, sday, grace, pay["buffer"], base["float_rate"], expected),
                    "previous": cf.previous(today, sday, grace, pay["buffer"])})
    if latest and latest["due_date"] and latest["total_due"] > 0:
        due = date.fromisoformat(latest["due_date"])
        pay["last_bill"] = {"statement": latest["stmt_date"], "amount": latest["total_due"], "due": latest["due_date"],
                            "pay_on": cf.pay_on(due, pay["buffer"]).isoformat(),
                            "days_to_pay": (cf.pay_on(due, pay["buffer"]) - today).days}

    return {
        "card": {**card, "rates": rates, "numbers": [c["last4"] for c in fam], "members": ids},
        "profile": {"classes": [{"id": c, "label": l, "rate": rates.get(c, 0)} for c, l in P["classes"]],
                    "emi_earns": P["emi_earns"], "has_leaks": bool(leaks), "rewards": any(v > 0 for v in rates.values()) or bool(P.get("points_from_statement") and pts_stmts)
                    or bool(P.get("realised_rewards") and realised),
                    "point_value": P.get("point_value", 0), "earned_label": P.get("earned_label")},
        "categories": categories,
        "points": ({"earned": points_total, "value": round(points_total * P["point_value"], 2),
                    "per_100": round(points_total / net * 100, 2) if net else 0,
                    "balance": next((s["points_balance"] for s in reversed(stmts) if s["points_balance"] is not None), None),
                    "redeem_at": P["redeem_at"], "unit": P.get("points_unit", "points"), "on_lines": sum(r["points"] or 0 for r in rows),
                    "months": [{"period_to": s["period_to"], "earned": s["points_earned"],
                                "value": round(s["points_earned"] * P["point_value"], 2)} for s in pts_stmts[-12:]]}
                   if P.get("points_from_statement") and pts_stmts else None),
        "benefits": benefits,
        "today": today.isoformat(),
        "totals": {
            "statements": len(stmts), "transactions": len(spend_rows),
            "spend": round(net, 2), "gross_spend": round(gross, 2), "refunds": round(refunds, 2),
            "earned": round(earned, 2), "earned_is_estimate": not reported, "cashback_calc": round(est, 2),
            "cashback_paid": round(float(sum(reported)), 2) if reported else None,
            "effective_rate": _pct(earned, net), "best_possible": round(net * max(rates.values() or [0]) / 100, 2),
            "fees_paid": round(fees, 2), "net_profit": round(earned - fees, 2),
            "avg_monthly_spend": round(net / max(len(cyc), 1), 2), "spend_12m": year_spend,
            "milestone_bonus": round(bonus, 2),
            "emi": round(sum(r["net"] for r in live if r["kind"] == "emi_principal"), 2),
            "since": rows[0]["tx_date"] if rows else None, "through": rows[-1]["tx_date"] if rows else None,
        },
        "by_class": by_class, "merchants": merchants[:25], "leaks": leaks,
        "months": months, "years": years, "latest": latest, "pay": pay,
        "fee": ({"annual_fee": card["annual_fee"], "waiver_spend": card["fee_waiver_spend"],
                 "year_spend": year_spend, "progress": _pct(year_spend, card["fee_waiver_spend"]),
                 "waived": year_spend >= card["fee_waiver_spend"],
                 "short_by": round(max(card["fee_waiver_spend"] - year_spend, 0), 2)}
                if card["fee_waiver_spend"] > 0 else None),
        "utilisation": (_pct(latest["total_due"], card["credit_limit"])
                        if latest and card["credit_limit"] > 0 else None),
    }


def overview(db, today=None):
    """Usage across every card: who spends how much, where, at what cost, and what is due next."""
    today = today or date.today()
    tiles, fy, seen_accounts, pay = [], {}, set(), []
    listed = list_cards(db)
    for c in listed:
        d = dashboard(db, c["id"], today)
        t, p = d["totals"], d["pay"]
        top = d["merchants"][0] if d["merchants"] else None
        closed = (c["status"] or "active") == "closed"
        tiles.append({
            "id": c["id"], "name": c["name"], "numbers": c["numbers"], "profile": c["profile"], "status": c["status"] or "active", "color": c["color"],
            "issuer": c["issuer"] or "", "network": c["network"] or "", "credit_limit": c["credit_limit"] or 0,
            "annual_fee": c["annual_fee"] or 0, "fee_waiver_spend": c["fee_waiver_spend"] or 0,
            "since": t["since"], "through": t["through"], "spend": t["spend"], "spend_12m": t["spend_12m"],
            "transactions": t["transactions"], "avg_ticket": round(t["spend"] / t["transactions"], 2) if t["transactions"] else 0,
            "emi": t["emi"], "emi_share": _pct(t["emi"], t["spend"]), "fees": t["fees_paid"],
            "fees_share": round(t["fees_paid"] / t["spend"] * 100, 2) if t["spend"] else 0,
            "earned": t["earned"], "earned_is_estimate": t["earned_is_estimate"], "rewards": d["profile"]["rewards"],
            "top_merchant": {"name": top["name"], "spend": top["spend"]} if top else None,
            "shared_with": p["shared_with"],
        })
        for y in d["years"]:
            fy.setdefault(y["fy"], {"fy": y["fy"], "by_card": {}, "total": 0.0})
            fy[y["fy"]]["by_card"][str(c["id"])] = y["spend"]
            fy[y["fy"]]["total"] = round(fy[y["fy"]]["total"] + y["spend"], 2)
        lb_now = p.get("last_bill")
        # A closed card has no next statement to wait for; only a bill already issued and not yet due is still owed.
        if closed and not (lb_now and lb_now["days_to_pay"] >= 0):
            continue
        if c["account_id"] not in seen_accounts and p.get("upcoming"):
            seen_accounts.add(c["account_id"])
            # A bill that has been issued and whose pay date has not passed comes first, with its amount;
            # otherwise the next statement.
            lb = p.get("last_bill")
            nxt = lb if lb and lb["days_to_pay"] >= 0 else p["upcoming"][0]
            pay.append({"card_id": c["id"], "name": c["name"], "cards": [c["name"]] + p["shared_with"],
                        "statement": nxt["statement"], "due": nxt["due"], "pay_on": nxt["pay_on"],
                        "days_to_pay": nxt["days_to_pay"], "verified": p["verified"], "stale": p["stale"],
                        "expected": lb["amount"] if nxt is lb else p.get("expected_bill", 0), "issued": nxt is lb})
    if not any(c.get("sort_order") for c in listed):
        tiles.sort(key=lambda t: t["status"] == "closed")           # until you place them, closed cards go last
    return {
        "today": today.isoformat(), "cards": tiles,
        "years": sorted(fy.values(), key=lambda f: f["fy"], reverse=True),
        "pay": sorted(pay, key=lambda x: x["pay_on"]),
        "totals": {"spend": round(sum(t["spend"] for t in tiles), 2), "spend_12m": round(sum(t["spend_12m"] for t in tiles), 2),
                   "fees": round(sum(t["fees"] for t in tiles), 2), "cards": len(tiles),
                   "active_cards": sum(1 for t in tiles if t["status"] != "closed")},
    }
