"""HDFC Bank (Tata Neu Infinity) statements: the credit-sign convention, wrapped lines, NeuCoins, the printed totals.

The synthetic statement reproduces the shapes of the real text: the rupee sign extracts as the letter C, a `+`
before the C marks a credit while `+ 45` is base NeuCoins, a payment line wraps onto a second line, and the
blocks appear out of order. Tests against the real PDFs run when the files and SPENDLENS_HDFC_PASSWORD exist.
"""
import glob
import os

import pytest

import cards
import cards_hdfc as hdfc
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = sorted(glob.glob(os.path.join(ROOT, "screenshot", "hdfc neu card", "*.pdf")))
PASSWORD = os.environ.get("SPENDLENS_HDFC_PASSWORD", "")
API = "/spendlens/api"


def stmt(prev="3,432.10", pay="3,779.75", purch="4,305.00", fin="0.00", due="21 Sep, 2026", total="C3,957.00", coins="154 193 154 5",
         lines=None, period="02 Aug, 2026 - 01 Sep, 2026", stmt_date="01 Sep, 2026"):
    lines = lines if lines is not None else [
        "31/07/2026| 00:00 Provisional Cr Upidelightful Gourme - 2 +  C 164.00 l",
        "31/07/2026| 00:00 Provisional Cr Upicowrks India Priv - 3 +  C 183.75 l",
        "02/08/2026| 19:02 EMI TATA DIGITAL PRIVATE + 45  C 3,000.00 l",
        "02/08/2026| 17:55 WWWBIGBASKETCOM  C 545.50 l",
        "03/08/2026| 07:58 BPPY CC PAYMENT DP016215075830JG7ii (Ref#",
        "ST262160083000010393711) +  C 3,432.00 l",
        "23/08/2026| 15:02 WWWBIGBASKETCOM  C 285.00 l",
        "30/08/2026| 20:30 UPI-Innovative RetailConcept  C 474.50 l",
    ]
    return "\n".join([
        "TOTAL AMOUNT DUE", total, "MINIMUM DUE", "C200.00", "DUE DATE", due, "NeuCoins with Bank", "188",
        "Opening NeuCoins with", "Bank", "NeuCoins Earned", "(Base+Bonus)", "NeuCoins Transferred", "to Tata Neu", "Adjusted/Lapsed", coins,
        "Domestic Transactions", "DATE & TIME TRANSACTION DESCRIPTION Base NeuCoins* AMOUNT PI", "SAURABH KUMAR ",
        *lines[:2], "Page 1 of 3",
        "PREVIOUS STATEMENT DUES PAYMENTS/CREDITS", "RECEIVED", "PURCHASES/DEBIT", "(Current Billing Cycle) FINANCE CHARGES",
        f"C{prev} C{pay} C{purch} C{fin}", "TOTAL CREDIT LIMIT", "(Including Cash) AVAILABLE CREDIT LIMIT AVAILABLE CASH LIMIT",
        "C3,70,000 C3,66,043 C1,48,000",
        "Tata Neu Infinity HDFC Bank Credit Card Statement", "Credit Card No.", "Alternate Account Number", "Statement Date", "Billing Period",
        "652926XXXXXX8146", "0001010410005778144", stmt_date, period,
        "Domestic Transactions", "DATE & TIME TRANSACTION DESCRIPTION Base NeuCoins* AMOUNT PI", *lines[2:], "Page 2 of 3",
    ])


def one(**kw):
    return hdfc.parse(stmt(**kw))[0]


# ------------------------------------------------------------------ reading

def test_detected_and_not_confused_with_other_banks():
    assert hdfc.detect(stmt())
    assert not hdfc.detect("SBI Card\nStatement Period: 12 Aug 26 to 11 Sep 26")
    assert not hdfc.detect("ICICI Bank\nStatement Period\n01/04/2025 TO 31/03/2026")


def test_header_cycle_and_card():
    p = one()
    assert (p["period_from"], p["period_to"], p["stmt_date"], p["due_date"]) == ("2026-08-02", "2026-09-01", "2026-09-01", "2026-09-21")
    assert p["card"] == {"issuer": "HDFC Bank", "last4": "8146", "name": "Tata Neu Infinity HDFC", "profile": "hdfc_neu"}
    assert (p["credit_limit"], p["total_due"]) == (370_000.0, 3957.0)


def test_a_plus_before_the_c_is_a_credit_and_a_plus_number_is_neucoins():
    t = {x["detail"][:14]: x for x in one()["txns"]}
    assert t["EMI TATA DIGIT"]["dc"] == "D" and t["EMI TATA DIGIT"]["points"] == 45
    assert t["Provisional Cr"]["dc"] == "C" and t["Provisional Cr"]["points"] == 0, "'+  C' is the credit sign, not coins"
    assert t["WWWBIGBASKETCO"]["dc"] == "D" and t["WWWBIGBASKETCO"]["points"] == 0


def test_a_payment_line_that_wraps_is_joined():
    pay = next(x for x in one()["txns"] if x["kind"] == "payment")
    assert pay["amount"] == 3432.0 and "ST262160083000010393711" in pay["ref"], "the reference sits on the wrapped line"
    assert pay["dc"] == "C"


def test_kinds_and_spend():
    p = one()
    k = {x["detail"][:10]: x["kind"] for x in p["txns"]}
    assert k["Provisiona"] == "refund" and k["BPPY CC PA"] == "payment" and k["UPI-Innova"] == "spend"
    assert p["purchases"] == 4305.0 and p["credits"] == 3779.75, "every credit, as the statement's payments/credits received"


def test_neucoins_are_read_not_estimated():
    p = one()
    assert p["points_earned"] == 193
    assert p["points_balance"] == 154 + 193 - 154 - 5 == 188, "opening + earned - transferred - lapsed"


def test_the_total_due_is_rounded_but_the_paise_are_kept_in_the_balance():
    p = one()
    assert p["total_due"] == 3957.0 and p["closing_balance"] == 3957.35


OCT = dict(prev="3,957.35", pay="3,957.00", purch="0.00", due="Nil", total="C0.00", coins="188 0 188 0", period="02 Sep, 2026 - 01 Oct, 2026",
           stmt_date="01 Oct, 2026", lines=["04/09/2026| 09:47 BPPY CC PAYMENT BD016247BAMAAANX24T (Ref#", "ST262480083000010230096) +  C 3,957.00 l"])


def test_nothing_due_prints_nil():
    p = one(**OCT)
    assert p["due_date"] is None and p["total_due"] == 0.0 and p["closing_balance"] == 0.35 and p["points_earned"] == 0


# ------------------------------------------------------------------ the proof

def test_lines_that_do_not_add_up_are_refused():
    with pytest.raises(ValueError, match="refusing to import"):
        hdfc.parse(stmt(purch="9,999.00"))
    with pytest.raises(ValueError, match="refusing to import"):
        hdfc.parse(stmt(pay="1.00"))


def test_a_dropped_line_is_caught():
    lines = [l for l in stmt().splitlines() if "285.00" not in l]
    with pytest.raises(ValueError, match="refusing to import"):
        hdfc.parse("\n".join(lines))


def test_a_wrong_credit_sign_would_be_caught_by_the_totals():
    """The sign convention is an inference; swapping it must fail the proof, not slip through."""
    flipped = stmt().replace("+  C 3,432.00", "C 3,432.00")
    with pytest.raises(ValueError, match="refusing to import"):
        hdfc.parse(flipped)


def test_coins_on_the_lines_cannot_exceed_the_printed_total():
    p = one(coins="154 20 154 0")        # lines carry 45, the statement says only 20 were earned
    assert p["points_earned"] == 20 and sum(t["points"] for t in p["txns"]) == 0


def test_not_an_hdfc_statement():
    with pytest.raises(ValueError):
        hdfc.parse("nothing here")


# ------------------------------------------------------------------ end to end

def _purge(db):
    ids = [r[0] for r in db.execute("SELECT id FROM cards WHERE issuer='HDFC Bank'")]
    if ids:
        q = ",".join("?" * len(ids))
        for t in ("card_txns", "card_statements", "card_merchant_rules"):
            db.execute(f"DELETE FROM {t} WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_perks WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM cards WHERE id IN ({q})", ids)
    db.execute("DELETE FROM card_accounts WHERE issuer='HDFC Bank' AND id NOT IN (SELECT account_id FROM cards)")
    db.commit()


@pytest.fixture
def hdfc_clean(seeded_db):
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


def test_the_card_the_cycle_and_the_neucoins_are_set_from_the_statement(client, hdfc_clean, monkeypatch):
    out = _upload(client, monkeypatch, {"sep.pdf": stmt()})[0]
    assert out["ok"] and out["card"] == "Tata Neu Infinity HDFC" and out["added"] == 7
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "HDFC Bank")
    assert (c["statement_day"], c["grace_days"], c["cycle_verified"], c["credit_limit"], c["profile"]) == (1, 20, 1, 370_000.0, "hdfc_neu")
    d = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()
    assert d["points"]["earned"] == 193 and d["points"]["unit"] == "NeuCoins" and d["points"]["redeem_at"] == 0
    assert d["totals"]["earned"] == 193.0 and d["totals"]["earned_is_estimate"] is False, "1 NeuCoin is Rs 1: read, not estimated"
    assert _upload(client, monkeypatch, {"sep.pdf": stmt()})[0]["added"] == 0


def test_the_cycle_is_learned_even_when_the_newest_statement_prints_no_due_date(client, hdfc_clean, monkeypatch):
    """Upload order must not matter: October owes nothing and prints 'Nil', but September's dates still set the cycle."""
    _upload(client, monkeypatch, {"oct.pdf": stmt(**OCT)})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "HDFC Bank")
    assert c["statement_day"] == 1 and c["cycle_verified"] == 0, "the day is known from the statement date, the due date is not"
    _upload(client, monkeypatch, {"sep.pdf": stmt()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "HDFC Bank")
    assert (c["statement_day"], c["grace_days"], c["cycle_verified"]) == (1, 20, 1), "an older statement still teaches the cycle"


# ------------------------------------------------------------------ the real statements

needs_real = pytest.mark.skipif(not REAL or not PASSWORD, reason="needs screenshot/hdfc neu card and SPENDLENS_HDFC_PASSWORD")


@needs_real
def test_every_real_hdfc_statement_balances():
    for p in REAL:
        s = hdfc.parse(cards.read_pdf(p, PASSWORD))[0]
        assert s["txns"] and s["card"]["last4"] == "8146" and s["points_earned"] is not None


@needs_real
def test_the_real_statements_import_once(client, hdfc_clean):
    def send():
        files = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in REAL]
        return client.post(f"{API}/cards/upload", data={"password": PASSWORD}, files=files).json()["files"]
    assert all(f["ok"] for f in send())
    assert sum(f["added"] for f in send()) == 0
