"""American Express activity exports (Excel): reading a workbook, the summary check, categories, re-downloads.

The synthetic workbooks mirror the real export: a `Transaction Details` sheet with a title carrying the
period, an account number, one row per transaction (charges positive, credits negative), and a
`Transaction Summary` sheet with the file's totals. They run without the private files; the tests against the
real downloads run when `screenshot/activity*.xlsx` is present.
"""
import glob
import io
import os

import openpyxl
import pytest

import cards
import cards_amex as ax
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = sorted(glob.glob(os.path.join(ROOT, "screenshot", "activity*.xlsx")))
API = "/spendlens/api"
TITLE = "American Express SmartEarn Credit Card / Jan 01, 2025 to Dec 31, 2025"

ROWS = [   # date, description, amount, reference, category
    ("11/24/2025", "PAYMENT RECEIVED. THANK YOU", -700.0, "S0001", ""),
    ("11/19/2025", "Cashfree*Swiggy         Bangal", 100.0, "AT001", "Entertainment-Restaurants"),
    ("11/16/2025", "RAZORPAY*Swiggy         Bangal", 245.0, "AT002", "Entertainment-Restaurants"),
    ("11/10/2025", "Razorpay*IXIGO          Gurgao", 1000.0, "AT003", "Travel-Rail Services"),
    ("11/10/2025", "1.8% CONVENIENCE FEE ON RAIL TICKET", 18.0, "AT003", "Travel-Rail Services"),
    ("11/10/2025", "GST/IGST@18%", 3.24, "AT003", ""),
    ("11/09/2025", "Pay with Points Credit-SafeKey", -83.75, "S0002", ""),
    ("11/02/2025", "ZOMATO LTD              GURGAO", 50.0, "AT004", "Entertainment-Restaurants"),
    ("11/01/2025", "FIRSTCRY PG             PUNE", -49.0, "S0003", "General Purchases-Clothing Stores"),   # a refund
]


def workbook(rows=ROWS, charges=None, credits=None, title=TITLE, account="XXXX-XXXXXX-32009", summary=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transaction Details"
    for r in (["Transaction Details", title], ["Prepared for", ""], ["TEST USER", ""], ["Account Number", ""], [account, ""], ["", ""],
              ["Date", "Description", "Amount", "Extended Details", "Appears On Your Statement As", "Address", "City/State",
               "Zip Code", "Country", "Reference", "Category"]):
        ws.append(r)
    for d, desc, amt, ref, cat in rows:
        ws.append([d, desc, amt, "", desc, "NO 1\nSOME ROAD", "", "560001", "INDIA", ref, cat])
    if summary:
        sm = wb.create_sheet("Transaction Summary")
        pos = round(sum(r[2] for r in rows if r[2] > 0), 2)
        neg = round(sum(r[2] for r in rows if r[2] < 0), 2)
        for r in (["Transaction Summary", title], ["Prepared for", ""], ["TEST USER", ""], ["Account Number", ""], [account, ""], ["", ""],
                  ["SUMMARY", ""], ["", "Total"], ["Payments & Credits", neg if credits is None else credits],
                  ["Charges", pos if charges is None else charges], ["Total", round(pos + neg, 2)]):
            sm.append(r)
    b = io.BytesIO()
    wb.save(b)
    b.seek(0)
    return b


def parsed(**kw):
    return ax.parse(cards.read_pdf(workbook(**kw), "", "x.xlsx"))[0]


# ------------------------------------------------------------------ reading a workbook

def test_a_workbook_is_recognised_by_its_bytes_not_its_name(tmp_path):
    b = workbook()
    assert cards._is_xlsx(b) and b.tell() == 0, "peeking must not move the reader"
    p = tmp_path / "notes.pdf"            # a workbook with the wrong extension is still a workbook
    p.write_bytes(workbook().getvalue())
    assert cards._is_xlsx(str(p))
    assert not cards._is_xlsx(io.BytesIO(b"%PDF-1.4 ..."))


def test_a_workbook_becomes_text_a_parser_can_read():
    t = cards.read_pdf(workbook(), "", "x.xlsx")
    assert t.startswith("#SHEET\tTransaction Details") and "#SHEET\tTransaction Summary" in t
    assert "NO 1 SOME ROAD" in t, "a line break inside a cell must not split the row"
    assert ax.detect(t) and not ax.detect("SBI Card statement")


def test_junk_that_is_neither_pdf_nor_spreadsheet_says_so():
    with pytest.raises(ValueError, match="not a readable PDF"):
        cards.read_pdf(io.BytesIO(b"hello"), "", "x.xlsx")


# ------------------------------------------------------------------ the rows

def test_period_card_and_account_come_from_the_file():
    p = parsed()
    assert (p["period_from"], p["period_to"]) == ("2025-01-01", "2025-12-31")
    assert p["card"] == {"issuer": "American Express", "last4": "32009", "name": "American Express SmartEarn Credit Card",
                         "profile": "amex_smartearn"}
    assert p["kind"] == "year" and p["due_date"] is None, "an activity export has no due date"


def test_kinds_signs_and_categories():
    t = {(x["ref"], x["detail"][:12]): x for x in parsed()["txns"]}
    assert t[("S0001", "PAYMENT RECE")]["kind"] == "payment" and t[("S0001", "PAYMENT RECE")]["dc"] == "C"
    assert t[("S0002", "Pay with Poi")]["kind"] == "cashback", "points spent as a bill credit are realised rewards"
    assert t[("S0003", "FIRSTCRY PG ")]["kind"] == "refund"
    assert t[("AT003", "GST/IGST@18%")]["kind"] == "fee" and t[("AT003", "1.8% CONVENI")]["kind"] == "fee"
    sw = t[("AT001", "Cashfree*Swi")]
    assert sw["kind"] == "spend" and sw["is_spend"] == 1 and sw["category"] == "Entertainment-Restaurants"
    assert sw["merchant"] == "Swiggy Bangal", "the aggregator and the padding are stripped from the shop"


def test_totals():
    p = parsed()
    assert p["purchases"] == 1395.0 and p["credits"] == 700.0 and p["fees"] == 21.24


def test_rows_that_share_a_reference_are_all_kept(client, amex_clean):  # noqa: F811
    """A charge, its convenience fee and the GST on it carry one reference; they are three transactions."""
    out = client.post(f"{API}/cards/upload", files=[("files", ("a.xlsx", workbook().getvalue(), "application/octet-stream"))]).json()["files"][0]
    assert out["ok"] and out["rows"] == 9 and out["added"] == 9, out


# ------------------------------------------------------------------ the proof

def test_rows_that_do_not_add_up_to_the_summary_are_refused():
    with pytest.raises(ValueError, match="refusing to import"):
        parsed(charges=9999.0)
    with pytest.raises(ValueError, match="refusing to import"):
        parsed(credits=-1.0)


def test_a_workbook_with_no_summary_cannot_be_verified():
    with pytest.raises(ValueError, match="cannot verify"):
        parsed(summary=False)


def test_a_title_without_a_period_is_refused():
    with pytest.raises(ValueError, match="title"):
        parsed(title="American Express SmartEarn Credit Card")


def test_a_dropped_row_is_caught_by_the_summary():
    short = workbook(rows=ROWS[:-1], charges=1395.0, credits=-833.75)   # summary still describes the full file
    with pytest.raises(ValueError, match="refusing to import"):
        ax.parse(cards.read_pdf(short, "", "x.xlsx"))


# ------------------------------------------------------------------ end to end

def _purge(db):
    ids = [r[0] for r in db.execute("SELECT id FROM cards WHERE issuer='American Express'")]
    if ids:
        q = ",".join("?" * len(ids))
        for t in ("card_txns", "card_statements", "card_merchant_rules"):
            db.execute(f"DELETE FROM {t} WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_perks WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM cards WHERE id IN ({q})", ids)
    db.execute("DELETE FROM card_accounts WHERE issuer='American Express' AND id NOT IN (SELECT account_id FROM cards)")
    db.commit()


@pytest.fixture
def amex_clean(seeded_db):
    db = database.get_db()
    _purge(db)
    db.close()
    yield
    db = database.get_db()
    _purge(db)
    db.close()


def _send(client, *books):
    files = [("files", (f"a{i}.xlsx", b.getvalue(), "application/octet-stream")) for i, b in enumerate(books)]
    return client.post(f"{API}/cards/upload", files=files).json()["files"]


def test_an_excel_upload_creates_the_card_and_a_second_upload_adds_nothing(client, amex_clean):
    out = _send(client, workbook())
    assert out[0]["ok"] and out[0]["card"] == "American Express SmartEarn Credit Card" and out[0]["parser"] == "American Express"
    assert _send(client, workbook())[0]["added"] == 0
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "American Express")
    assert c["last4"] == "32009" and c["profile"] == "amex_smartearn"


def test_an_overlapping_download_adds_only_the_new_rows(client, amex_clean):
    """A later download that repeats part of an earlier one: references de-duplicate the overlap."""
    _send(client, workbook())
    later_rows = ROWS[:3] + [("12/02/2025", "ZOMATO LTD              GURGAO", 75.0, "AT099", "Entertainment-Restaurants")]
    later = workbook(rows=later_rows, title="American Express SmartEarn Credit Card / Jan 01, 2025 to Dec 31, 2025")
    out = _send(client, later)[0]
    assert out["ok"] and out["added"] == 1 and out["skipped"] == 3


def test_the_dashboard_shows_categories_and_redeemed_rewards(client, amex_clean):
    _send(client, workbook())
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "American Express")
    d = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()
    assert d["totals"]["earned"] == 83.75 and d["totals"]["earned_is_estimate"] is False, "the points spent as credits"
    assert d["profile"]["earned_label"] == "Rewards redeemed" and d["profile"]["rewards"] is True
    cats = {x["name"]: x["spend"] for x in d["categories"]}
    assert cats["Travel-Rail Services"] == 1000.0, "the 18 convenience fee is a fee, not spend"
    assert cats["Entertainment-Restaurants"] == 395.0
    assert "General Purchases-Clothing Stores" not in cats, "a refund-only category has no net spend"
    assert d["totals"]["spend"] == 1346.0, "1,395 of charges less the 49 refund"
    assert d["pay"]["needs_cycle"] is True, "an activity export has no billing cycle: it is asked for, not invented"
    assert d["pay"].get("habit") is None


def test_the_cycle_can_be_entered_and_pay_timing_follows(client, amex_clean):
    _send(client, workbook())
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "American Express")
    body = {"profile": None, "rates": {}, "statement_day": 12, "grace_days": 18, "pay_buffer_days": 2, "float_rate": 7}
    assert client.put(f"{API}/cards/{c['id']}", json=body).status_code == 200
    pay = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()["pay"]
    assert pay["needs_cycle"] is False and pay["habit"]["paid"] > 0 and pay["verified"] is True


# ------------------------------------------------------------------ the real downloads

needs_real = pytest.mark.skipif(len(REAL) < 1, reason="needs screenshot/activity*.xlsx")


@needs_real
def test_every_real_amex_export_passes_its_own_summary():
    for f in REAL:
        p = ax.parse(cards.read_pdf(f))[0]
        assert p["txns"] and p["card"]["last4"] == "32009"


@needs_real
def test_the_real_exports_import_once(client, amex_clean):
    files = [("files", (os.path.basename(f), open(f, "rb"), "application/octet-stream")) for f in REAL]
    first = client.post(f"{API}/cards/upload", files=files).json()["files"]
    assert all(x["ok"] for x in first), [x for x in first if not x["ok"]]
    files = [("files", (os.path.basename(f), open(f, "rb"), "application/octet-stream")) for f in REAL]
    assert sum(x["added"] for x in client.post(f"{API}/cards/upload", files=files).json()["files"]) == 0
