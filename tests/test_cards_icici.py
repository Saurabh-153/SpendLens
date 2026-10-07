"""ICICI statements, multi-card handling, the duplicate-row fix, and refunds in the earn engine.

Synthetic text mirrors the real layout (wrapped descriptions, negative credits, tax lines with
no reference number, page furniture in the middle of a record), so the suite is meaningful
without the private PDFs. Tests against the real files run when they are present.
"""
import glob
import os

import pytest

import cards
import cards_icici as ic
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICICI_PDFS = sorted(glob.glob(os.path.join(ROOT, "screenshot", "FY*.pdf")))
API = "/spendlens/api"

FAKE = """\
Customer Name Card Account No
MR TEST USER
4315 XXXX XXXX 0002
Statement Period
01/04/2025 TO 31/03/2026
TRANSACTION DETAILS
Card Number : 4315 XXXX XXXX 0002
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
02-APR-25 74766515092513861261094 IND*AMAZON.IN - GROCER
HTTP://WWW.AM IN
0.00 737.00
05-APR-25 74766515095513021501360 IND*AMAZON HTTP://WWW.AM IN 0.00 485.00
07-APR-25 BD015097BAHAAAN0CSXV BBPS Payment received 0.00 -1,000.00
The category of service:Credit & Debit Card,Charge Card or Other payment Card service.
REGISTERED OFFICE IS ICICI BANK LIMITED,"LANDMARK",RACE COURSE CIRCLE, VADODARA 390 007 , INDIA.
TRANSACTION DETAILS
Card Number : 4315 XXXX XXXX 0002
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
10-APR-25 74766515100514246987122 SWIGGY Bengaluru IN 0.00 300.00
12-APR-25 74766515102514365977449 SWIGGY Bengaluru IN 0.00 -100.00
16-APR-25 Principal Amount Amortization - <1/6> 0.00 1,000.00
16-APR-25 IGST-CI@18% 0.00 18.00
16-APR-25 Interest Amount Amortization - <1/6> 0.00 100.00
16-APR-25 INSTANT EMI OFFUS CONVERSION 0.00 0.00
20-APR-25 261180577116 INFINITY PAYMENT RECEIVED, THANK YOU 0.00 -1,500.00
Sincerely,
Team ICICI Bank
"""
# net spend = 737 + 485 + 300 - 100 (refund) + 1000 (EMI principal) = 2,422
# fees = 18 + 100 = 118; payments = 1,000 + 1,500 = 2,500


def test_detect_tells_the_banks_apart():
    assert ic.detect(FAKE)
    assert not ic.detect("SBI Card statement\nStatement Period: 12 Aug 26 to 11 Sep 26")
    assert not cards.detect_sbi(FAKE)


def test_every_line_is_read_including_wrapped_and_untaxed_ones():
    p = ic.parse(FAKE)[0]
    assert len(p["txns"]) == 9, "the zero-amount EMI marker is dropped, nothing else"
    wrapped = next(t for t in p["txns"] if t["ref"] == "74766515092513861261094")
    assert wrapped["amount"] == 737.0 and wrapped["dc"] == "D" and "GROCER" in wrapped["detail"]
    tax = next(t for t in p["txns"] if t["detail"].startswith("IGST"))
    assert tax["ref"] == "" and tax["kind"] == "fee", "tax lines carry no reference number"


def test_signs_and_kinds():
    k = {t["detail"][:14]: t for t in ic.parse(FAKE)[0]["txns"]}
    assert k["BBPS Payment r"]["kind"] == "payment" and k["BBPS Payment r"]["dc"] == "C"
    assert k["INFINITY PAYME"]["kind"] == "payment"
    assert k["Principal Amou"]["kind"] == "emi_principal" and k["Principal Amou"]["emi"] == 1
    refund = next(t for t in ic.parse(FAKE)[0]["txns"] if t["dc"] == "C" and t["kind"] == "refund")
    assert refund["amount"] == 100.0, "a negative merchant line is a refund, stored as a positive amount"


def test_net_spend_and_the_cash_identity():
    p = ic.parse(FAKE)[0]
    assert p["purchases"] == 2422.0, "737 + 485 + 300 - 100 refund + 1000 EMI principal"
    assert p["fees"] == 118.0 and p["credits"] == 2500.0
    billed = sum(t["amount"] for t in p["txns"] if t["dc"] == "D")
    credited = sum(t["amount"] for t in p["txns"] if t["dc"] == "C")
    # spend + fees - payments = what is still owed
    assert round(p["purchases"] + p["fees"] - p["credits"], 2) == round(billed - credited, 2) == 40.0


def test_period_card_and_statement_day():
    p = ic.parse(FAKE)[0]
    assert (p["period_from"], p["period_to"]) == ("2025-04-01", "2026-03-31")
    c = p["card"]
    assert (c["issuer"], c["last4"], c["bin"], c["profile"]) == ("ICICI Bank", "0002", "4315", "generic"), \
        "a new ICICI card is not assumed to be the Amazon Pay card: its reward scheme is unknown"
    assert c["name"].startswith("ICICI Bank") and c["name"].endswith("0002")
    assert (c["first_seen"], c["last_seen"]) == ("2025-04-02", "2025-04-20")
    assert p["statement_day_hint"] == 16, "EMI instalments post on the statement date"
    assert p["kind"] == "year" and p["due_date"] is None


def test_an_unreadable_line_rejects_the_whole_statement():
    """The coverage check: a line that cannot be read is a transaction that would go missing."""
    broken = FAKE.replace("0.00 485.00", "garbled")
    with pytest.raises(ValueError, match="refusing to import"):
        ic.parse(broken)


def test_not_an_icici_statement_is_rejected():
    with pytest.raises(ValueError):
        ic.parse("nothing here")


def test_page_furniture_is_not_glued_onto_a_transaction():
    rows = ic.parse(FAKE)[0]["txns"]
    assert not any("REGISTERED OFFICE" in t["detail"] or "Card Number" in t["detail"] for t in rows)


# ------------------------------------------------------------------ earn: refunds and EMI

def test_a_refund_takes_its_reward_back():
    txns = [{"tx_date": "2026-01-01", "merchant": "PYU*SHOP", "amount": 1000.0, "is_spend": 1, "kind": "spend"},
            {"tx_date": "2026-01-05", "merchant": "PYU*SHOP", "amount": 400.0, "is_spend": 0, "kind": "refund"}]
    assert cards.earn(txns, cards.DEFAULT_RULES) == 30.0, "5% of 1000 less 5% of the 400 refunded"
    assert txns[1]["cashback"] == -20.0


def test_emi_earns_nothing_where_the_card_says_so():
    txns = [{"tx_date": "2026-01-01", "merchant": "EMI instalment", "amount": 1000.0, "is_spend": 1,
             "kind": "emi_principal", "emi": 1}]
    assert cards.earn(txns, cards.AMAZON_RULES, cards.PROFILES["icici_amazon"]["rates"],
                      cap=0, default=cards.OTHER, emi_earns=False) == 0.0
    assert txns[0]["cls"] == "excluded"
    # ...but on SBI an EMI conversion does earn, which ten real statements proved
    txns[0]["emi"], txns[0]["merchant"] = 1, "PYU*SHOP"
    assert cards.earn(txns, cards.DEFAULT_RULES, emi_earns=True) == 50.0


def test_a_cap_of_zero_means_uncapped():
    txns = [{"tx_date": "2026-01-01", "merchant": "PYU*SHOP", "amount": 1_000_000.0, "is_spend": 1}]
    assert cards.earn(txns, cards.DEFAULT_RULES, cap=0) == 50000.0


@pytest.mark.parametrize("merchant,expected", [
    ("AMAZON", "amazon"), ("IND*AMAZON.IN - GROCER", "amazon"), ("AMAZON PAY IN GROCERY", "amazon"),
    ("AMAZON RECHARGES", "partner"), ("AMAZON IRCTC", "partner"), ("SWIGGY INSTAMART", "partner"),
    ("BHARTI AIRTEL LIMITED", "other"), ("HPCL PETROL", "excluded"),
])
def test_amazon_pay_classification(merchant, expected):
    assert cards.classify(merchant, cards.AMAZON_RULES, cards.OTHER) == expected


# ------------------------------------------------------------------ the duplicate-row fix

SBI = """\
SBI Card
for Statement Period: 12 Aug 26 to 11 Sep 26
9,000.00
200.00
4,00,000.00
1,20,000.00
3,91,000.00
1,20,000.00
1,000.00
120.00
0.00
11 Sep 2026
01 Oct 2026
9,000.00
0.00
XXXX XXXX XXXX XX82
TRANSACTIONS FOR TEST
12 Aug 26 COMPASS INDIA FOOD S   aRoadSector   IND 40.00 D
12 Aug 26 COMPASS INDIA FOOD S   aRoadSector   IND 40.00 D
13 Aug 26 PYU*FLIPKART INTERNET  Bangalore     IND 40.00 D
statement Date. T&C Apply
5
"""


def test_two_identical_lines_on_one_day_are_both_kept(seeded_db):
    """The bug this guards: a hash on (date, amount, text) collapsed two real Rs 40 purchases into one."""
    db = database.get_db()
    try:
        card = cards.get_card(db)
        parsed = cards.parse_statement(SBI)
        assert parsed["purchases"] == 120.0
        _sid, added = cards.save_statement(db, card, parsed, "dup-test")
        assert added == 3
        stored = db.execute("""SELECT ROUND(SUM(amount),2) FROM card_txns
                               WHERE statement_id IN (SELECT id FROM card_statements WHERE file='dup-test')""").fetchone()[0]
        assert stored == 120.0, "stored spend must equal the statement's own purchases total"
        _sid, again = cards.save_statement(db, card, parsed, "dup-test")
        assert again == 0, "re-importing must add nothing"
    finally:
        db.execute("DELETE FROM card_txns WHERE statement_id IN (SELECT id FROM card_statements WHERE file='dup-test')")
        db.execute("DELETE FROM card_statements WHERE file='dup-test'")
        db.commit()
        db.close()


def test_the_billing_cycle_is_read_from_a_statement_that_states_it(seeded_db):
    db = database.get_db()
    try:
        card = cards.get_card(db)
        parsed = cards.parse_statement(SBI)
        cards.save_statement(db, card, parsed, "cycle-test")
        row = cards.get_card(db, card["id"])
        assert (row["statement_day"], row["grace_days"], row["cycle_verified"]) == (11, 20, 1)
    finally:
        db.execute("DELETE FROM card_txns WHERE statement_id IN (SELECT id FROM card_statements WHERE file='cycle-test')")
        db.execute("DELETE FROM card_statements WHERE file='cycle-test'")
        db.commit()
        db.close()


# ------------------------------------------------------------------ cards from statements

def test_a_new_card_is_created_from_its_statement_once(seeded_db):
    db = database.get_db()
    try:
        info = ic.parse(FAKE)[0]["card"]
        a, b = cards.resolve_card(db, info), cards.resolve_card(db, info)
        assert a["id"] == b["id"], "the same statement must not create the card twice"
        assert a["profile"] == "generic" and a["last4"] == "0002"
        assert cards.card_rates(a) == {"other": 0}, "no reward scheme is assumed, so no reward is invented"
        assert a["cycle_verified"] == 0, "a cycle that was not read from a statement stays unverified"
        assert a["account_id"], "every card sits on a billing account"
        amazon = cards.resolve_card(db, {"issuer": "ICICI Bank", "last4": "9999", "profile": "icici_amazon", "name": "Amazon Pay"})
        assert cards.card_rates(amazon) == {"amazon": 5, "partner": 2, "other": 1, "excluded": 0}
        sbi = cards.resolve_card(db, {"issuer": "SBI Card", "last4": "82", "profile": "sbi_cashback"})
        assert sbi["id"] != a["id"] and sbi["profile"] == "sbi_cashback"
    finally:
        db.execute("DELETE FROM card_perks WHERE card_id IN (SELECT id FROM cards WHERE issuer='ICICI Bank')")
        db.execute("DELETE FROM cards WHERE issuer='ICICI Bank'")
        db.commit()
        db.close()


def test_the_dashboard_is_empty_not_broken_for_a_card_with_no_rows(seeded_db):
    db = database.get_db()
    try:
        d = cards.dashboard(db)
        assert d["totals"]["spend"] == 0 and d["months"] == [] and d["merchants"] == []
        assert d["fee"] is not None, "the SBI card has an annual fee and a waiver threshold"
    finally:
        db.close()


# ------------------------------------------------------------------ settings

def _settings(card, **over):
    body = {"credit_limit": 0, "annual_fee": 0, "fee_waiver_spend": 0, "cashback_cap": 0,
            "rates": {"online": 5, "offline": 1, "excluded": 0}, "statement_day": 11, "grace_days": 20,
            "pay_buffer_days": 1, "float_rate": 7}
    body.update(over)
    return body


@pytest.mark.parametrize("over,msg", [
    ({"statement_day": 0}, "Statement day"), ({"statement_day": 32}, "Statement day"),
    ({"grace_days": 0}, "Days to the due date"), ({"grace_days": 61}, "Days to the due date"),
    ({"pay_buffer_days": 20}, "safety margin"), ({"pay_buffer_days": -1}, "safety margin"),
    ({"float_rate": 31}, "Rate must be"), ({"rates": {"online": 150}}, "Rates must be"),
    ({"rates": {"amazon": 5}}, "reward classes"),
])
def test_settings_are_validated(client, seeded_db, over, msg):
    cid = client.get(f"{API}/cards").json()[0]["id"]
    r = client.put(f"{API}/cards/{cid}", json=_settings(None, **over))
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_saving_the_cycle_marks_it_verified_and_changes_the_pay_dates(client, seeded_db):
    before = client.get(f"{API}/cards/dashboard").json()
    c = before["card"]
    original = {k: c[k] for k in ("credit_limit", "annual_fee", "fee_waiver_spend", "cashback_cap", "rates",
                                  "statement_day", "grace_days", "float_rate")}
    original["pay_buffer_days"] = c["pay_buffer_days"]
    assert client.put(f"{API}/cards/{c['id']}", json={**original, "statement_day": 5, "grace_days": 18}).status_code == 200
    try:
        card = next(x for x in client.get(f"{API}/cards").json() if x["id"] == c["id"])
        assert (card["statement_day"], card["grace_days"], card["cycle_verified"]) == (5, 18, 1)
    finally:  # put the card back exactly as it was, terms included
        assert client.put(f"{API}/cards/{c['id']}", json=original).status_code == 200
    after = client.get(f"{API}/cards/dashboard").json()["card"]
    assert (after["annual_fee"], after["fee_waiver_spend"], after["credit_limit"]) == (c["annual_fee"], c["fee_waiver_spend"], c["credit_limit"])


def test_upload_creates_the_card_and_never_mixes_cards(client, seeded_db, monkeypatch):
    """Two cards' statements in one upload must land on two different cards."""
    import io
    import pypdf

    def pdf_bytes():
        w = pypdf.PdfWriter()
        w.add_blank_page(width=200, height=200)
        b = io.BytesIO()
        w.write(b)
        return b.getvalue()

    texts = {"icici.pdf": FAKE, "sbi.pdf": SBI}
    monkeypatch.setattr(cards, "read_pdf", lambda source, password="", name="": texts[name])
    try:
        files = [("files", (n, pdf_bytes(), "application/pdf")) for n in texts]
        out = client.post(f"{API}/cards/upload", files=files).json()["files"]
        assert all(f["ok"] for f in out), out
        by = {f["file"]: f for f in out}
        assert by["icici.pdf"]["card"].startswith("ICICI Bank") and by["sbi.pdf"]["card"] == "CASHBACK SBI Card"
        assert by["icici.pdf"]["card_id"] != by["sbi.pdf"]["card_id"]
        again = client.post(f"{API}/cards/upload", files=[("files", ("icici.pdf", pdf_bytes(), "application/pdf"))]).json()["files"]
        assert again[0]["added"] == 0, "re-uploading adds nothing"
        d = client.get(f"{API}/cards/dashboard", params={"card_id": by["icici.pdf"]["card_id"]}).json()
        assert d["totals"]["spend"] == 2422.0 and d["pay"]["needs_cycle"] is False   # statement day read from the EMI lines
        assert [c["id"] for c in d["profile"]["classes"]] == ["other"] and d["profile"]["rewards"] is False
    finally:  # the fixture database is shared across the session: leave it as found
        db = database.get_db()
        db.execute("DELETE FROM card_txns WHERE statement_id IN (SELECT id FROM card_statements WHERE file IN ('icici.pdf','sbi.pdf'))")
        db.execute("DELETE FROM card_statements WHERE file IN ('icici.pdf','sbi.pdf')")
        db.execute("DELETE FROM card_perks WHERE card_id IN (SELECT id FROM cards WHERE issuer='ICICI Bank')")
        db.execute("DELETE FROM cards WHERE issuer='ICICI Bank'")
        db.commit()
        db.close()


# ------------------------------------------------------------------ the real files (no password needed)

needs_icici = pytest.mark.skipif(not ICICI_PDFS, reason="needs screenshot/FY*.pdf")


@needs_icici
def test_every_real_icici_statement_reads_completely():
    total = 0
    for path in ICICI_PDFS:
        for p in ic.parse(cards.read_pdf(path)):
            assert p["txns"], os.path.basename(path)
            total += len(p["txns"])
            assert {t["kind"] for t in p["txns"]} <= {"spend", "refund", "payment", "cashback", "emi_principal", "fee"}
    assert total > 0


@needs_icici
def test_the_real_icici_books_balance():
    """Net spend + fees = payments + cashback + what is still owed. Exact, because the cash adds up."""
    rows = []
    for path in ICICI_PDFS:
        for p in ic.parse(cards.read_pdf(path)):
            rows += p["txns"]
    billed = sum(t["amount"] for t in rows if t["dc"] == "D")
    credited = sum(t["amount"] for t in rows if t["dc"] == "C")
    owed = billed - credited
    assert -3000 < owed < 3000, f"{owed:,.0f} is still owing after five years: lines are missing or mis-signed"
    net = lambda *k: sum(t["amount"] if t["dc"] == "D" else -t["amount"] for t in rows if t["kind"] in k)
    paid = sum(t["amount"] for t in rows if t["kind"] == "payment") + sum(t["amount"] for t in rows if t["kind"] == "cashback")
    assert net("spend", "refund", "emi_principal") + net("fee") == pytest.approx(paid + owed, abs=0.5)
