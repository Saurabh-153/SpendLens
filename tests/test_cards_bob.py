"""Bank of Baroda (BOBCARD) statements: two text layouts, printed totals, reward points, missing statements.

The synthetic statements mirror the two real forms: the monthly layout extracts one field per line, the
table layout extracts columns separated by runs of spaces. Both must give the same answer. The tests
against the real PDFs run when the files and the password (SPENDLENS_BOB_PASSWORD) are present.
"""
import glob
import os
from datetime import date

import pytest

import cards
import cards_bob as bob
import cards_icici as ic
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOB_PDFS = sorted(glob.glob(os.path.join(ROOT, "screenshot", "bob eterna", "*")))
BOB_PASSWORD = os.environ.get("SPENDLENS_BOB_PASSWORD", "")
API = "/spendlens/api"


def monthly(opening=1000.0, payments=500.0, purchases=300.0, closing=800.0, due_flag="DR", extra_lines="", points=(100, 25, 0, 125),
            header_money=None):
    """The monthly layout, one field per line, with Hindi labels in between like the real one."""
    money = header_money or [f"₹ {opening:,.2f}", f"₹ {payments:,.2f}", f"₹ {purchases:,.2f}", f"₹ {closing:,.2f}"]
    return "\n".join([
        "Credit Card Monthly Statement", "Statement Date : ", "25/09/2026", "|   Statement Period : ", "26 Aug, 2026 to 25 Sep, 2026",
        "Tax Invoice to: ", "MR. TEST USER", "Card", " : RUPAY ETERNA", "Card No: 356162XXXXXX1395", "Sanctioned Credit Limit: ", "₹200,000",
        "भुगतान", "देय", "Payment Due Date", "Minimum Amount Due", "Total Amount Due", "14/10/2026", "Pay Now", "200.00", "₹ ",
        f"{closing:,.2f}{due_flag}", "Credit Limit", "₹ 200,000", "₹ 199,200.00", "₹ 80,000.00", "₹ 80,000.00",
        *money, "Online Pay I.D. ", "0007934060000362889", "Account Summary",
        *[str(p) for p in points], " Bonus/Reward Points Summary",
        "तारीख", "Date", "Ref. No.", "Particulars", "Reward", "Points", "Source", "Currency", "Amount",
        "SAURABH KUMAR ", "(PRIMARY CARD - 1395)",
        "26/08/2026", "RAZORPAY PAYMENT MOBILEAPP- API", "INR", "500.00", "500.00 ", "CR",
        "28/08/2026", "R4679Z", "UPI-SHOP_ONE_", "7", "INR", "100.00", "100.00 ", "DR",
        "29/08/2026", "R98127", "AMAZON", "356", "18", "INR", "200.00", "200.00 ", "DR",
        extra_lines,
        "Transaction Details", "Please register your Mobile Number & Email ID via the BOBCARD mobile app", "Page ", "1", " of ", "5",
    ])


def table():
    """The same statement in the table layout: columns separated by runs of spaces, 'amount DR' on one line."""
    return "\n".join([
        "                 25/09/2026                         26 Aug, 2026 To 25 Sep, 2026",
        "   MR. TEST USER",
        "   LAYOUT, VARTHUR                     XXXXXX********1395          2,00,000.00",
        "   Card :   RUPAY BOB-RUPAY ETERNA",
        "   State :   KARNATAKA                       14/10/2026",
        "   Place of Supply :                         200.00        800.00 DR",
        "   2,00,000.00        1,99,200.00        80,000.00        80,000.00",
        "   1,000.00           500.00             300.00           800.00",
        "   0007934060000362889",
        "   100      25       0       125",
        "   26/08/2026      RAZORPAY PAYMENT MOBILEAPP- API                          INR      500.00      500.00 CR",
        "   28/08/2026      R4679Z      UPI-SHOP ONE                    7            INR      100.00      100.00 DR",
        "   29/08/2026      R98127      AMAZON            356     18                INR      200.00      200.00 DR",
        "Please register your Mobile No. and Email ID via the BOBCARD mobile app or portal for regular alerts. Alternatively,",
        "   Page 1 of 5",
    ])


def one(text):
    return bob.parse(text)[0]


def keyed(p, points=True):
    return sorted((t["tx_date"], t["amount"], t["dc"], t["detail"], t["ref"]) + ((t["points"],) if points else ())
                  for t in p["txns"])


# ------------------------------------------------------------------ both layouts, one answer

def test_both_layouts_are_detected_and_other_banks_are_not():
    assert bob.detect(monthly()) and bob.detect(table())
    assert not bob.detect("SBI Card statement\nStatement Period: 12 Aug 26 to 11 Sep 26")
    assert not bob.detect("ICICI Bank\nStatement Period\n01/04/2025 TO 31/03/2026")
    assert not cards.detect_sbi(monthly()) and not ic.detect(monthly())


def test_the_monthly_layout_reads_completely():
    p = one(monthly())
    assert (p["period_from"], p["period_to"], p["stmt_date"], p["due_date"]) == ("2026-08-26", "2026-09-25", "2026-09-25", "2026-10-14")
    assert len(p["txns"]) == 3 and p["credit_limit"] == 200_000.0 and p["total_due"] == 800.0
    assert (p["points_earned"], p["points_balance"]) == (25, 125)
    assert p["card"] == {"issuer": "Bank of Baroda", "last4": "1395", "name": "BOB Eterna", "profile": "bob_eterna"}
    assert p["kind"] == "cycle" and p["validation"] == "total"


def test_the_table_layout_gives_exactly_the_same_statement():
    a, b = one(monthly()), one(table())
    assert keyed(a) == keyed(b), "the same statement in either layout must de-duplicate against itself"
    for k in ("period_from", "period_to", "stmt_date", "due_date", "total_due", "credits", "purchases", "points_earned",
              "points_balance", "credit_limit"):
        assert a[k] == b[k], k
    assert b["card"]["last4"] == "1395", "the table layout masks the number differently"


def test_underscores_in_a_merchant_are_spaces_so_the_layouts_agree():
    """The monthly layout prints UPI-SHOP_ONE_ where the table layout shows UPI-SHOP ONE."""
    assert [t["detail"] for t in one(monthly())["txns"] if t["ref"] == "R4679Z"] == ["UPI-SHOP ONE"]


# ------------------------------------------------------------------ what a line means

def rows(text):
    return {t["ref"] or t["detail"]: t for t in one(text)["txns"]}


def test_upi_spends_carry_points_and_card_spends_carry_a_country_code_then_points():
    r = rows(monthly())
    assert r["R4679Z"]["points"] == 7, "after UPI- a lone number is the points"
    assert r["R98127"]["points"] == 18, "after the country code 356 comes the points"
    assert r["R98127"]["ccy"] == "" and r["R98127"]["is_spend"] == 1


def test_a_card_spend_with_only_a_country_code_has_no_points():
    extra = "\n".join(["30/08/2026", "R52599", "MORE", "356", "INR", "50.00", "50.00 ", "DR"])
    # keep the printed totals honest: add the line and move the totals with it
    p = one(monthly(purchases=350.0, closing=850.0, extra_lines=extra, points=(100, 25, 0, 125)))
    t = next(x for x in p["txns"] if x["ref"] == "R52599")
    assert t["points"] == 0 and t["amount"] == 50.0


def test_a_foreign_spend_is_marked_by_its_currency():
    extra = "\n".join(["30/08/2026", "R11111", "ACME ABROAD", "840", "12", "USD", "10.00", "840.00 ", "DR"])
    p = one(monthly(purchases=1140.0, closing=1640.0, extra_lines=extra, points=(100, 37, 0, 137)))   # 7 + 18 + 12 points
    t = next(x for x in p["txns"] if x["ref"] == "R11111")
    assert t["ccy"] == "USD" and t["amount"] == 840.0 and t["points"] == 12


@pytest.mark.parametrize("detail,dc,kind", [
    ("RAZORPAY PAYMENT MOBILEAPP- API", "C", "payment"), ("BBPS-PAYMENT", "C", "payment"), ("BILLDESK PAYMENT-MOBILE APP", "C", "payment"),
    ("1234 Effortless Cashback RuPay CC", "C", "cashback"), ("SURCHARGE WAIVER", "C", "cashback"),
    ("Flipkart Internet Priv", "C", "refund"), ("AMAZON", "D", "spend"), ("GST ON FEE", "D", "fee"),
])
def test_line_kinds(detail, dc, kind):
    assert bob._kind({"detail": detail, "dc": dc}) == kind


# ------------------------------------------------------------------ the arithmetic that makes an import trustworthy

def test_lines_that_do_not_add_up_to_the_printed_totals_are_refused():
    with pytest.raises(ValueError, match="refusing to import"):
        bob.parse(monthly(purchases=999.0, closing=1499.0))


def test_a_dropped_line_is_caught_by_the_totals():
    text = monthly().replace("\n".join(["29/08/2026", "R98127", "AMAZON", "356", "18", "INR", "200.00", "200.00 ", "DR"]), "")
    with pytest.raises(ValueError, match="refusing to import"):
        bob.parse(text)


def test_a_zero_opening_balance_prints_only_three_figures():
    """A first statement: opening 0 is not printed as a number, leaving payments, purchases, closing."""
    p = one(monthly(opening=0.0, payments=500.0, purchases=300.0, closing=-200.0, header_money=["₹ 500.00", "₹ 300.00", "₹ -200.00"]))
    assert p["credits"] == 500.0


def test_a_credit_balance_prints_with_no_leading_digit():
    """June: closing -0.21 printed as '₹ -.21', which an ordinary number pattern does not match."""
    p = one(monthly(opening=428.43, payments=500.0, purchases=300.0, closing=228.43,
                    header_money=["₹ 428.43", "₹ 500.00", "₹ 300.00", "₹ 228.43"]))
    assert p["total_due"] == 228.43
    p = one(monthly(opening=0.50, payments=500.0, purchases=300.0, closing=-199.50, due_flag="CR",
                    header_money=["₹ 0.50", "₹ 500.00", "₹ 300.00", "₹ -199.50"]))
    assert p["total_due"] == 0.0, "a credit balance owes nothing"


def test_the_header_is_not_swallowed_when_nothing_is_due():
    """With nothing due there is no DR in the header, so the header ran straight into the first transaction."""
    p = one(monthly(due_flag=""))
    assert len(p["txns"]) == 3 and p["points_earned"] == 25


def test_reward_points_on_the_lines_need_not_equal_the_printed_total():
    """Bonus and adjustment points belong to no line; the printed total is the truth, the money check stays strict."""
    p = one(monthly(points=(100, 40, 0, 140)))
    assert p["points_earned"] == 40 and sum(t["points"] for t in p["txns"]) == 25


# ------------------------------------------------------------------ unreadable text

def test_text_with_one_character_per_line_is_recognised_as_garbled():
    assert cards._garbled("\n".join("x" * 1 for _ in range(500)))
    assert not cards._garbled(monthly())


def test_it_is_not_a_bob_statement_without_a_period():
    with pytest.raises(ValueError):
        bob.parse("BOBCARD but nothing else")


# ------------------------------------------------------------------ missing statements

def stmt(i, f, t):
    return {"id": i, "period_from": f, "period_to": t}


def test_unbroken_statements_are_one_run():
    runs, seg, missing = cards._segments([stmt(1, "2026-01-26", "2026-02-25"), stmt(2, "2026-02-26", "2026-03-25")], 25)
    assert len(runs) == 1 and seg == {1: 0, 2: 0} and missing == []


def test_a_missing_statement_splits_the_runs_and_is_named():
    runs, seg, missing = cards._segments([stmt(1, "2026-06-26", "2026-07-25"), stmt(2, "2026-08-26", "2026-09-25")], 25)
    assert len(runs) == 2 and seg == {1: 0, 2: 1}
    assert missing == ["2026-08-25"], "the 25 Aug statement is the one that is missing"


def test_two_missing_statements_are_both_named():
    _, _, missing = cards._segments([stmt(1, "2026-01-26", "2026-02-25"), stmt(2, "2026-04-26", "2026-05-25")], 25)
    assert missing == ["2026-03-25", "2026-04-25"]


# ------------------------------------------------------------------ end to end (synthetic)

def _purge(db):
    ids = [r[0] for r in db.execute("SELECT id FROM cards WHERE issuer='Bank of Baroda'")]
    if ids:
        q = ",".join("?" * len(ids))
        for t in ("card_txns", "card_statements", "card_merchant_rules"):
            db.execute(f"DELETE FROM {t} WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_perks WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM cards WHERE id IN ({q})", ids)
    db.execute("DELETE FROM card_accounts WHERE issuer='Bank of Baroda' AND id NOT IN (SELECT account_id FROM cards)")
    db.commit()


@pytest.fixture
def bob_clean(seeded_db):
    db = database.get_db()
    _purge(db)
    db.close()
    yield
    db = database.get_db()
    _purge(db)
    db.close()


def _upload(client, monkeypatch, texts):
    import io
    import pypdf
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    monkeypatch.setattr(cards, "read_pdf", lambda source, password="", name="": texts[name])
    return client.post(f"{API}/cards/upload", files=[("files", (n, b.getvalue(), "application/pdf")) for n in texts]).json()["files"]


def test_both_layouts_of_one_statement_import_once(client, bob_clean, monkeypatch):
    out = _upload(client, monkeypatch, {"a.pdf": monthly(), "b.pdf": table()})
    assert all(f["ok"] for f in out), out
    assert out[0]["added"] == 3 and out[1]["added"] == 0, "the second layout of the same statement adds nothing"
    again = _upload(client, monkeypatch, {"a.pdf": monthly()})
    assert again[0]["added"] == 0


def test_the_card_is_created_with_its_cycle_read_from_the_statement(client, bob_clean, monkeypatch):
    _upload(client, monkeypatch, {"a.pdf": monthly()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "Bank of Baroda")
    assert (c["name"], c["last4"], c["profile"]) == ("BOB Eterna", "1395", "bob_eterna")
    assert (c["statement_day"], c["grace_days"], c["cycle_verified"], c["credit_limit"]) == (25, 19, 1, 200_000.0)


def test_rewards_are_the_printed_points_times_the_value_of_a_point(client, bob_clean, monkeypatch):
    _upload(client, monkeypatch, {"a.pdf": monthly()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "Bank of Baroda")
    d = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()
    assert d["points"]["earned"] == 25 and d["points"]["balance"] == 125 and d["points"]["redeem_at"] == 1000
    assert d["totals"]["earned"] == 6.25 and d["totals"]["earned_is_estimate"] is False, "25 points at Rs 0.25, and it is read, not estimated"
    assert d["points"]["value"] == 6.25 and d["profile"]["rewards"] is True and d["profile"]["point_value"] == 0.25
    assert d["points"]["on_lines"] == 25


# ------------------------------------------------------------------ the real statements

needs_bob = pytest.mark.skipif(not BOB_PDFS or not BOB_PASSWORD, reason="needs screenshot/bob eterna and SPENDLENS_BOB_PASSWORD")


@needs_bob
def test_every_real_bob_statement_reads_and_its_points_are_consistent():
    """Each statement parses (which already requires its lines to equal its printed totals), the cycle is
    stated on every one, and the points on the lines never exceed the printed earned total."""
    parsed = []
    for p in BOB_PDFS:
        parsed += bob.parse(cards.read_pdf(p, BOB_PASSWORD))
    assert len(parsed) >= 8
    for s in parsed:
        assert s["txns"] and s["due_date"] and s["stmt_date"] == s["period_to"]
        assert sum(t["points"] for t in s["txns"]) <= s["points_earned"]


@needs_bob
def test_the_two_real_february_layouts_agree():
    monthly_f = [p for p in BOB_PDFS if p.endswith("250226.pdf")]
    table_f = [p for p in BOB_PDFS if os.path.basename(p).startswith("CC_STMT")]
    if not monthly_f or not table_f:
        pytest.skip("both February files are needed")
    a = bob.parse(cards.read_pdf(monthly_f[0], BOB_PASSWORD))[0]
    b = bob.parse(cards.read_pdf(table_f[0], BOB_PASSWORD))[0]
    assert keyed(a, points=False) == keyed(b, points=False), "every line, amount and reference agrees"
    assert (a["points_earned"], a["total_due"], a["due_date"]) == (b["points_earned"], b["total_due"], b["due_date"])
    # but the table layout's per-line points contradict its own printed total (one purchase shows 152, the
    # monthly layout 76), so they are dropped and only the printed total is kept
    assert sum(t["points"] for t in b["txns"]) == 0 and sum(t["points"] for t in a["txns"]) > 0


@needs_bob
def test_the_real_statements_import_once_and_a_missing_month_is_not_a_late_payment(client, bob_clean):
    import os as _os

    def send():
        files = [("files", (_os.path.basename(p), open(p, "rb"), "application/pdf")) for p in BOB_PDFS]
        return client.post(f"{API}/cards/upload", data={"password": BOB_PASSWORD}, files=files).json()["files"]

    first = send()
    assert all(f["ok"] for f in first), [f for f in first if not f["ok"]]
    assert sum(f["added"] for f in send()) == 0, "uploading every file again must add nothing"
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "Bank of Baroda")
    pay = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()["pay"]
    if pay["missing_statements"]:
        assert pay["habit"]["late_amount"] == 0, "a bill whose payment fell in a missing cycle is not a late payment"


def test_line_points_that_exceed_the_printed_total_are_dropped_not_trusted():
    """A statement whose lines claim more points than its own header is contradicting itself."""
    p = one(monthly(points=(100, 20, 0, 120)))          # lines carry 7 + 18 = 25 points, header says 20
    assert p["points_earned"] == 20 and sum(t["points"] for t in p["txns"]) == 0
    assert len(p["txns"]) == 3, "the money lines are untouched"
