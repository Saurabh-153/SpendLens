"""Several cards on one statement: sections, shared bills, replaced card numbers, the overview.

The synthetic statement mirrors what a real ICICI account list looks like: a section per card
number, an account-level `0000` section for fees, payments posted under one card that settle
the others, and a card re-issued under a new number.
"""
import glob
import io
import os
import random

import pypdf
import pytest

import cards
import cards_icici as ic
import database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICICI_PDFS = sorted(glob.glob(os.path.join(ROOT, "screenshot", "FY*.pdf")))
API = "/spendlens/api"

#: Timeline, all on one bill (header account ...7018):
#:   ...7000  5 Apr 2021 - 10 Jun 2021     \  re-issued: 7018 starts 10 days after 7000 stops
#:   ...7018  20 Jun 2021 - 30 Sep 2021    /
#:   ...4005  1 Aug 2021 - 1 Mar 2022      a different card: in use at the same time as 7018
#: Fees sit in the account-level 0000 section; every payment is posted under 4005.
MULTI = """\
Customer Name Card Account No
MR TEST USER
{header}
Statement Period
01/04/2021 TO 31/03/2022
TRANSACTION DETAILS
Card Number : 0000 XXXX XXXX 1001
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
15-JUL-21 feelevy CP1 Reward redemption handling 0.00 99.00
01-SEP-21 feelevy CP2 Reward redemption handling 0.00 99.00
01-FEB-22 feelevy CP3 Reward redemption handling 0.00 99.00
TRANSACTION DETAILS
Card Number : 5241 XXXX XXXX 7000
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
05-APR-21 100000001 SHOP ONE Mumbai 0.00 1,000.00
10-JUN-21 100000002 SHOP TWO Mumbai 0.00 500.00
TRANSACTION DETAILS
Card Number : 5241 XXXX XXXX 7018
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
20-JUN-21 100000003 SHOP THREE Mumbai 0.00 700.00
30-SEP-21 100000004 SHOP FOUR Mumbai 0.00 300.00
TRANSACTION DETAILS
Card Number : 4501 XXXX XXXX 4005
Date Ref. Number Transaction Details Currency International
amount Amount(in ` )
01-AUG-21 100000005 SHOP FIVE Mumbai 0.00 2,000.00
10-AUG-21 300000001 UPI Payment Received 0.00 -1,500.00
05-OCT-21 300000002 UPI Payment Received 0.00 -1,000.00
01-MAR-22 100000006 SHOP SIX Mumbai 0.00 400.00
20-FEB-22 300000003 UPI Payment Received 0.00 -2,000.00
Sincerely,
Team ICICI Bank
"""
HEADER_7018 = "5241 XXXX XXXX 7018"
HEADER_4005 = "4501 XXXX XXXX 4005"


def multi(header=HEADER_7018):
    return MULTI.format(header=header)


def by_last4(parsed):
    return {p["card"]["last4"]: p for p in parsed}


def purge(db):
    """Remove every ICICI card the tests created, so the shared fixture database is left as found."""
    ids = [r[0] for r in db.execute("SELECT id FROM cards WHERE issuer='ICICI Bank'")]
    if ids:
        q = ",".join("?" * len(ids))
        db.execute(f"DELETE FROM card_txns WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_statements WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_merchant_rules WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM card_perks WHERE card_id IN ({q})", ids)
        db.execute(f"DELETE FROM cards WHERE id IN ({q})", ids)
    db.execute("DELETE FROM card_accounts WHERE issuer='ICICI Bank' AND id NOT IN (SELECT account_id FROM cards)")
    db.commit()


@pytest.fixture
def icici_clean(seeded_db):
    db = database.get_db()
    purge(db)
    db.close()
    yield
    db = database.get_db()
    purge(db)
    db.close()


def pdf_bytes():
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def upload(client, monkeypatch, texts):
    """Upload fake PDFs whose text layer is given: {name: text}."""
    monkeypatch.setattr(cards, "read_pdf", lambda source, password="", name="": texts[name])
    files = [("files", (n, pdf_bytes(), "application/pdf")) for n in texts]
    return client.post(f"{API}/cards/upload", files=files).json()["files"]


def confirm_cycle(client, card_id, day=10, grace=20):
    """What a user does when a statement does not print the cycle: enter it from a monthly statement."""
    body = {"profile": None, "rates": {}, "statement_day": day, "grace_days": grace, "pay_buffer_days": 1, "float_rate": 7}
    assert client.put(f"{API}/cards/{card_id}", json=body).status_code == 200


def test_without_a_printed_cycle_the_pay_panel_asks_for_one(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank")
    pay = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()["pay"]
    assert pay["needs_cycle"] is True and "habit" not in pay, "no cycle known: no pay dates are invented"


# ------------------------------------------------------------------ parsing a file with several cards

def test_one_entry_per_real_card_and_account_rows_are_not_a_card():
    parsed = ic.parse(multi())
    assert sorted(p["card"]["last4"] for p in parsed) == ["4005", "7000", "7018"], "the 0000 section is not a card"
    assert all(p["card"]["bin"] != "0000" for p in parsed)


def test_every_line_lands_on_exactly_one_card():
    """3 fees + 2 + 2 purchases on the older numbers + 5 lines on 4005 = 12, none lost, none doubled."""
    parsed = ic.parse(multi())
    refs = [(t["tx_date"], t["amount"], t["dc"], t["detail"]) for p in parsed for t in p["txns"]]
    assert len(refs) == 12 and len(set(refs)) == 12


def test_account_level_fees_go_to_the_card_in_use_that_day():
    p = by_last4(ic.parse(multi()))
    fee = lambda last4: sorted(t["tx_date"] for t in p[last4]["txns"] if t["kind"] == "fee")
    assert fee("7018") == ["2021-07-15", "2021-09-01"], "15 Jul: only 7018 live. 1 Sep: 7018 and 4005 live, so the statement's own card"
    assert fee("4005") == ["2022-02-01"], "1 Feb 2022: only 4005 is live"
    assert fee("7000") == []


def test_a_tie_between_live_cards_goes_to_the_card_the_statement_is_addressed_to():
    p = by_last4(ic.parse(multi(HEADER_4005)))
    assert [t["tx_date"] for t in p["4005"]["txns"] if t["kind"] == "fee"] == ["2021-09-01", "2022-02-01"]
    assert [t["tx_date"] for t in p["7018"]["txns"] if t["kind"] == "fee"] == ["2021-07-15"]


def test_payments_stay_under_the_card_they_were_posted_to():
    p = by_last4(ic.parse(multi()))
    assert sum(t["amount"] for t in p["4005"]["txns"] if t["kind"] == "payment") == 4500.0
    assert p["7000"]["credits"] == 0 and p["7018"]["credits"] == 0


def test_education_fees_are_a_purchase_not_a_bank_fee():
    """'FEES COLLECTION A/C' is a school being paid; a bank charge starts 'FEE ' or 'FEELEVY'."""
    assert ic._kind("FEES COLLECTION A/C DE Kolkata IN") == "merchant"
    assert ic._kind("feelevy CP003756895 Reward redemption handling") == "fee"
    assert ic._kind("Fee     199 : 0%") == "fee"


# ------------------------------------------------------------------ which numbers are one card

def card(i, lo, hi):
    return {"id": i, "_lo": lo, "_hi": hi, "name": f"c{i}"}


def numbers(chains):
    return sorted(sorted(c["id"] for c in ch) for ch in chains)


def test_a_replacement_follows_its_predecessor():
    chains = cards.lineage([card(1, "2020-04-01", "2021-02-23"), card(2, "2021-02-23", "2022-01-01")])
    assert numbers(chains) == [[1, 2]], "touching dates: the new number starts the day the old one stops"


def test_a_quiet_spell_while_the_new_card_arrives_is_allowed():
    """The real data had 95 days without a purchase between two numbers of one card."""
    assert numbers(cards.lineage([card(1, "2020-05-01", "2021-02-19"), card(2, "2021-05-25", "2022-01-01")])) == [[1, 2]]


def test_a_card_opened_years_later_is_not_a_replacement():
    assert numbers(cards.lineage([card(1, "2020-01-01", "2022-01-01"), card(2, "2025-03-30", "2026-03-01")])) == [[1], [2]]


def test_cards_used_at_the_same_time_are_two_cards():
    assert numbers(cards.lineage([card(1, "2022-01-01", "2025-12-05"), card(2, "2025-03-30", "2026-03-01")])) == [[1], [2]]


def test_the_gap_limit_is_exact():
    ok = cards.lineage([card(1, "2021-01-01", "2021-03-01"), card(2, "2021-06-29", "2021-09-01")])   # 120 days
    no = cards.lineage([card(1, "2021-01-01", "2021-03-01"), card(2, "2021-06-30", "2021-09-01")])   # 121 days
    assert numbers(ok) == [[1, 2]] and numbers(no) == [[1], [2]]


def test_the_grouping_does_not_depend_on_input_order():
    """Statements arrive in any order; the answer must not."""
    base = [card(1, "2020-04-01", "2021-02-23"), card(2, "2021-02-23", "2022-01-01"),
            card(3, "2022-01-21", "2025-12-05"), card(4, "2025-03-30", "2026-03-15")]
    want = numbers(cards.lineage(base))
    assert want == [[1, 2, 3], [4]]
    for seed in range(20):
        shuffled = base[:]
        random.Random(seed).shuffle(shuffled)
        assert numbers(cards.lineage(shuffled)) == want


def test_a_card_that_never_spent_stands_alone():
    assert numbers(cards.lineage([card(1, "2021-01-01", "2021-06-01"), card(2, None, None)])) == [[1], [2]]


# ------------------------------------------------------------------ importing, end to end

def test_cards_on_one_statement_share_an_account_and_a_replacement_is_one_card(client, icici_clean, monkeypatch):
    out = upload(client, monkeypatch, {"multi.pdf": multi()})
    assert out[0]["ok"] and len(out[0]["cards"]) == 3, out
    db = database.get_db()
    try:
        accts = {r[0] for r in db.execute("SELECT account_id FROM cards WHERE issuer='ICICI Bank'")}
        assert len(accts) == 1, "cards listed on one statement share a bill"
    finally:
        db.close()
    physical = [c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"]
    assert sorted(c["numbers"] for c in physical) == [["4005"], ["7000", "7018"]]
    again = upload(client, monkeypatch, {"multi.pdf": multi()})
    assert again[0]["added"] == 0, "re-uploading adds nothing"


def test_a_payment_posted_under_one_card_settles_the_whole_bill(client, icici_clean, monkeypatch):
    """All 4,500 of payments sit under 4005, but they settle spend on 7000 and 7018 as well."""
    upload(client, monkeypatch, {"multi.pdf": multi()})
    physical = {tuple(c["numbers"]): c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"}
    confirm_cycle(client, physical[("4005",)]["id"])    # the cycle is shared, so one confirmation covers both
    a = client.get(f"{API}/cards/dashboard", params={"card_id": physical[("7000", "7018")]["id"]}).json()
    b = client.get(f"{API}/cards/dashboard", params={"card_id": physical[("4005",)]["id"]}).json()
    assert a["pay"]["habit"]["paid"] == b["pay"]["habit"]["paid"] > 0, "one bill, one set of payments"
    assert a["pay"]["shared_with"] == [physical[("4005",)]["name"]]
    assert b["pay"]["shared_with"] == [physical[("7000", "7018")]["name"]]
    # but spend stays per card
    assert a["totals"]["spend"] == 2500.0 and b["totals"]["spend"] == 2400.0
    assert a["card"]["numbers"] == ["7000", "7018"]


def test_card_numbers_and_members_are_reported(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["numbers"] == ["7000", "7018"])
    assert len(c["members"]) == 2 and c["last4"] == "7018", "the newest number stands for the card"


def test_the_overview_adds_up(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    confirm_cycle(client, next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank")["id"])
    o = client.get(f"{API}/cards/overview").json()
    icici = [c for c in o["cards"] if c["name"].startswith("ICICI Bank")]
    assert sorted(c["spend"] for c in icici) == [2400.0, 2500.0]
    fy = next(y for y in o["years"] if y["fy"] == "FY2021")
    assert fy["total"] == pytest.approx(sum(fy["by_card"].values()), abs=0.01), "the year's total is its cards' sum"
    assert o["totals"]["cards"] == len(o["cards"])
    assert len(o["pay"]) <= len(o["cards"]), "one pay line per bill, not per card"
    icici_pay = [p for p in o["pay"] if p["name"].startswith("ICICI Bank")]
    assert len(icici_pay) == 1 and len(icici_pay[0]["cards"]) == 2, "the two ICICI cards are one bill"


# ------------------------------------------------------------------ settings across a card and a bill

def test_the_cycle_applies_to_every_card_on_the_bill_but_the_name_only_to_one(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    cs = [c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"]
    target = next(c for c in cs if c["numbers"] == ["4005"])
    body = {"name": "My travel card", "profile": "generic", "credit_limit": 0, "annual_fee": 0, "fee_waiver_spend": 0,
            "cashback_cap": 0, "rates": {"other": 0}, "statement_day": 10, "grace_days": 22, "pay_buffer_days": 2,
            "float_rate": 6}
    assert client.put(f"{API}/cards/{target['id']}", json=body).status_code == 200
    after = [c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"]
    assert {(c["statement_day"], c["grace_days"], c["pay_buffer_days"], c["cycle_verified"]) for c in after} == {(10, 22, 2, 1)}, \
        "one bill, one due date, so the cycle is shared"
    assert sorted(c["name"] for c in after if c["numbers"] == ["4005"]) == ["My travel card"]
    assert not any(c["name"] == "My travel card" for c in after if c["numbers"] != ["4005"])


def test_changing_the_reward_scheme_resets_rates_and_reclassifies(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["numbers"] == ["4005"])
    body = {"profile": "icici_amazon", "rates": {}, "statement_day": 15, "grace_days": 20, "pay_buffer_days": 1, "float_rate": 7}
    assert client.put(f"{API}/cards/{c['id']}", json=body).status_code == 200
    d = client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).json()
    assert d["profile"]["rewards"] is True
    assert [k["id"] for k in d["profile"]["classes"]] == ["amazon", "partner", "other", "excluded"]
    assert d["card"]["rates"] == {"amazon": 5, "partner": 2, "other": 1, "excluded": 0}


def test_an_unknown_reward_scheme_is_refused(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank")
    r = client.put(f"{API}/cards/{c['id']}", json={"profile": "made_up", "rates": {}, "statement_day": 5,
                                                   "grace_days": 20, "pay_buffer_days": 1, "float_rate": 7})
    assert r.status_code == 400 and "reward scheme" in r.json()["detail"]


def test_a_merchant_correction_must_use_the_cards_own_classes(client, icici_clean, monkeypatch):
    upload(client, monkeypatch, {"multi.pdf": multi()})
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank")
    bad = client.post(f"{API}/cards/merchant-rule", json={"pattern": "SHOP", "cls": "online", "card_id": c["id"]})
    assert bad.status_code == 400 and "other" in bad.json()["detail"], "SBI's classes are not valid on a usage-only card"


# ------------------------------------------------------------------ the real files (no password needed)

def _has_the_two_card_account():
    try:
        return any("5241 XXXX XXXX 5007" in cards.read_pdf(p) for p in ICICI_PDFS)
    except Exception:
        return False


needs_icici = pytest.mark.skipif(not _has_the_two_card_account(), reason="needs the two-card ICICI account statements in screenshot/")


@needs_icici
def test_the_real_account_is_two_cards_on_one_bill(client, icici_clean):
    def send():
        files = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in ICICI_PDFS]
        return client.post(f"{API}/cards/upload", files=files).json()["files"]

    first = send()
    assert all(f["ok"] for f in first), [f for f in first if not f["ok"]]
    # the real files include the Amazon Pay card's own statements as well as the two-card account
    physical = [c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"]
    series = [c["numbers"] for c in physical]
    assert ["5007"] in series, f"the newer card is its own card: {series}"
    assert ["7000", "7018", "4005"] in series, f"numbers re-issued one after another are one card: {series}"
    second = send()
    assert sum(f["added"] for f in second) == 0, "uploading every file again must add nothing"


@needs_icici
def test_the_real_account_books_balance_across_both_cards(client, icici_clean):
    files = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in ICICI_PDFS]
    client.post(f"{API}/cards/upload", files=files)
    db = database.get_db()
    try:
        for (acct,) in db.execute("SELECT DISTINCT account_id FROM cards WHERE issuer='ICICI Bank'").fetchall():
            row = db.execute("""SELECT SUM(CASE WHEN dc='D' THEN amount ELSE -amount END), COUNT(DISTINCT card_id)
                                FROM card_txns WHERE card_id IN (SELECT id FROM cards WHERE account_id=?)""", (acct,)).fetchone()
            if row[1] > 1:   # the shared account: payments under one card settle the others
                assert abs(row[0]) < 5000, f"{row[0]:,.0f} is unaccounted for across the shared bill"
    finally:
        db.close()
