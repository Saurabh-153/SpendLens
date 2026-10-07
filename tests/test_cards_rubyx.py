"""ICICI Rubyx: the reward scheme, the yearly milestone, lounge access, and row-identity stability.

Terms come from the bank's own page (icici.bank.in, Rubyx key privileges): 4 points per Rs 100
international, 2 domestic, 1 on utility and insurance, none on fuel; 3,000 points at Rs 3 lakh a year
and 1,500 per further lakh up to 15,000; 2 domestic lounge visits a quarter when the previous
quarter's spend exceeded Rs 75,000. The value of a point is not on that page, so it is an assumption
(Rs 0.25) and every rate is editable.
"""
from datetime import date

import pytest

import cards
import cards_icici as ic
import database
from test_cards_accounts import icici_clean, multi, upload  # noqa: F401  (fixtures and helpers)

API = "/spendlens/api"


# ------------------------------------------------------------------ row identity must never drift

def test_a_rows_identity_is_pinned():
    """Every stored row is found again by this hash. If the key format or the parsed text of a line
    changes, re-uploading an old statement duplicates it. A real incident: a harmless-looking tidy of
    'THANK' to 'THANK YOU' changed 228 payment hashes and a re-upload added all 228 again."""
    pay = {"tx_date": "2025-04-20", "amount": 1500.0, "dc": "C", "detail": "INFINITY PAYMENT RECEIVED, THANK",
           "ref": "261180577116"}
    sbi = {"tx_date": "2026-08-12", "amount": 40.0, "dc": "D", "detail": "COMPASS INDIA FOOD S   aRoadSector   IND", "ref": ""}
    assert cards._row_hash(1, pay) == "9a436e2a800bfe4a9a767a4c42cee541bb2bb1b7"
    assert cards._row_hash(1, sbi) == "4936fc5a770ff7be22a7ced8b12e2eebcb49e9ba"
    assert cards._row_hash(1, sbi, 1) == "1c1eddf01f7891ea52d83884b9c27fc58255ef7a", "the 2nd identical line has its own hash"


def test_the_parsed_text_of_a_payment_line_is_unchanged():
    stmt = """\
Statement Period
01/04/2025 TO 31/03/2026
Card Number : 4501 XXXX XXXX 4005
20-APR-25 261180577116 INFINITY PAYMENT RECEIVED, THANK YOU 0.00 -1,500.00
10-JUL-25 FASTAG IMB 0.00 500.00
Sincerely,
Team ICICI Bank
"""
    rows = {t["amount"]: t for t in ic.parse(stmt)[0]["txns"]}
    assert rows[1500.0]["detail"] == "INFINITY PAYMENT RECEIVED, THANK", "'YOU' is not a currency; dropped as it always was"
    assert rows[1500.0]["ccy"] == "" and rows[500.0]["ccy"] == ""


def test_stored_hashes_are_reproducible_from_the_stored_rows(real_db_copy):
    """Against the real database: every stored row's hash can be recomputed from its own fields."""
    import sqlite3
    conn = sqlite3.connect(str(real_db_copy))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT card_id, tx_date, amount, dc, detail, ref, row_hash FROM card_txns")]
    if not rows:
        pytest.skip("no card rows in the real database")
    bad = [r for r in rows if r["row_hash"] not in {cards._row_hash(r["card_id"], r, n) for n in range(8)}]
    assert not bad, f"{len(bad)} stored rows cannot be recognised by the current hash, e.g. {bad[0]}"


# ------------------------------------------------------------------ currency

def test_a_foreign_currency_line_is_marked():
    stmt = """\
Statement Period
01/04/2024 TO 31/03/2025
Card Number : 4501 XXXX XXXX 4005
28-SEP-24 74766513000000000000001 Amazon web services aws.amazon.co US* USD 1.82 158.69
Sincerely,
Team ICICI Bank
"""
    t = ic.parse(stmt)[0]["txns"][0]
    assert t["ccy"] == "USD" and t["amount"] == 158.69


# ------------------------------------------------------------------ the scheme

def rb(merchant):
    return cards.classify(merchant, cards.RUBYX_RULES, cards.DOMESTIC)


@pytest.mark.parametrize("merchant,expected", [
    ("HPCL-COMMANDANT 8 BN T", "excluded"), ("BHARAT PETROLEUM", "excluded"),   # fuel earns nothing
    ("HDFC LIFE INSUR CYBS SI", "utility"), ("MAX LIFE CYBS SI MUMBAI", "utility"),
    ("PAYU*WWW.POLICYBAZAAR.C", "utility"), ("AIRTEL GURGAON", "utility"),
    ("INDANE GAS AGENCY", "utility"), ("SPENCERS RETAIL LIMITE", "domestic"),
    ("VEGAS CASINO", "domestic"),            # 'GAS' must be a word, not a substring
    ("SWIGGY", "domestic"), ("AMAZON", "domestic"),
])
def test_rubyx_classification(merchant, expected):
    assert rb(merchant) == expected


def test_rates_are_points_times_the_value_of_a_point():
    r = cards.PROFILES["icici_rubyx"]["rates"]
    assert r == {"international": 1.0, "domestic": 0.5, "utility": 0.25, "excluded": 0}
    assert r["international"] == 4 * cards.POINT_VALUE and r["domestic"] == 2 * cards.POINT_VALUE and r["utility"] == 1 * cards.POINT_VALUE


def test_earn_pays_each_class_its_own_rate():
    P = cards.PROFILES["icici_rubyx"]

    def row(merchant, ccy="", emi=0):
        return {"tx_date": "2026-01-01", "merchant": merchant, "amount": 10000.0, "is_spend": 1, "kind": "spend", "ccy": ccy, "emi": emi}

    txns = [row("SWIGGY"), row("HDFC LIFE INSUR"), row("HPCL PETROL"), row("AWS", ccy="USD"), row("EMI instalment", emi=1)]
    total = cards.earn(txns, P["rules"], P["rates"], cap=0, default=P["default"], emi_earns=False)
    assert [t["cashback"] for t in txns] == [50.0, 25.0, 0.0, 100.0, 0.0]   # 2, 1, 0, 4 points per Rs 100 at Rs 0.25; EMI nothing
    assert total == 175.0 and txns[3]["cls"] == "international"


def test_fuel_stays_excluded_even_when_billed_in_a_foreign_currency():
    P = cards.PROFILES["icici_rubyx"]
    t = [{"tx_date": "2026-01-01", "merchant": "SHELL PETROL", "amount": 5000.0, "is_spend": 1, "kind": "spend", "ccy": "EUR"}]
    cards.earn(t, P["rules"], P["rates"], cap=0, default=P["default"])
    assert t[0]["cls"] == "excluded" and t[0]["cashback"] == 0


# ------------------------------------------------------------------ the yearly milestone

@pytest.mark.parametrize("spend,points", [
    (0, 0), (299_999, 0), (300_000, 3000), (399_999, 3000), (400_000, 4500), (500_000, 6000),
    (1_100_000, 15_000), (1_200_000, 15_000), (5_000_000, 15_000),   # capped at 15,000 a year
])
def test_milestone_points(spend, points):
    assert cards.milestone_points(spend) == points


def live(d, amount, cls="domestic", merchant="SHOP"):
    return {"_d": d, "net": amount, "cls": cls, "merchant": merchant, "tx_date": d.isoformat()}


def test_the_milestone_counts_by_financial_year_and_skips_fuel():
    rows = [live(date(2024, 5, 1), 250_000), live(date(2024, 12, 1), 60_000),
            live(date(2024, 6, 1), 90_000, cls="excluded", merchant="HPCL")]       # fuel does not count
    b = cards.rubyx_benefits(rows, [], date(2025, 2, 1), 0.25)
    fy = {y["fy"]: y for y in b["milestone"]["years"]}
    assert fy["FY2024"]["spend"] == 310_000 and fy["FY2024"]["points"] == 3000 and fy["FY2024"]["value"] == 750.0
    cur = b["milestone"]["current"]
    assert cur["fy"] == "FY2024" and cur["points"] == 3000 and cur["next_at"] == 400_000 and cur["to_go"] == 90_000 and cur["next_points"] == 4500


def test_the_next_milestone_before_reaching_the_first():
    b = cards.rubyx_benefits([live(date(2026, 5, 1), 100_000)], [], date(2026, 6, 1), 0.25)
    cur = b["milestone"]["current"]
    assert cur["next_at"] == 300_000 and cur["to_go"] == 200_000 and cur["next_points"] == 3000 and cur["points"] == 0


# ------------------------------------------------------------------ lounge access

def test_lounge_visits_follow_the_previous_quarter_and_need_more_than_the_threshold():
    rows = [live(date(2025, 1, 15), 80_000),                  # Q1: over 75,000
            live(date(2025, 4, 15), 50_000),                  # Q2
            live(date(2025, 7, 15), 75_000)]                  # Q3: exactly 75,000 does NOT exceed it
    q = {x["quarter"]: x for x in cards.rubyx_benefits(rows, [], date(2025, 12, 1), 0.25)["lounge"]["quarters"]}
    assert q["2025 Q1"]["earns_next"] is True and q["2025 Q1"]["entitled"] is False
    assert q["2025 Q2"]["entitled"] is True, "Q1's spend earns visits in Q2"
    assert q["2025 Q2"]["earns_next"] is False
    assert q["2025 Q3"]["earns_next"] is False, "75,000 exactly does not exceed 75,000"
    assert q["2025 Q3"]["entitled"] is False


def test_the_year_boundary_for_quarters():
    assert cards._prev_quarter("2026 Q1") == "2025 Q4" and cards._prev_quarter("2026 Q3") == "2026 Q2"


def test_lounge_swipes_are_counted_and_fuel_spend_does_not_qualify_a_quarter():
    rows = [live(date(2025, 1, 5), 60_000), live(date(2025, 2, 5), 40_000, cls="excluded", merchant="HPCL"),
            live(date(2025, 2, 6), 2, merchant="Dreamfolks Services Pr Gurgaon"),
            live(date(2025, 3, 6), 2, merchant="Dreamfolks Services Pr Gurgaon")]
    q = cards.rubyx_benefits(rows, [], date(2025, 6, 1), 0.25)["lounge"]["quarters"][0]
    assert q["spend"] == 60_004 and q["earns_next"] is False, "40,000 of fuel is not counted, so the quarter stays under 75,000"
    assert q["swipes"] == 2


# ------------------------------------------------------------------ redemption cost

def test_redeeming_points_costs_99_plus_gst_each():
    fees = [{"detail": "feelevy CP1 Reward redemption handling", "amount": 99.0},
            {"detail": "feelevy CP2 Reward redemption handling", "amount": 99.0},
            {"detail": "IGST-CI@18%", "amount": 17.82}]
    r = cards.rubyx_benefits([], fees, date(2026, 1, 1), 0.25)["redemptions"]
    assert r["count"] == 2 and r["per_redemption"] == 116.82 and r["cost"] == pytest.approx(233.64, abs=0.01)


# ------------------------------------------------------------------ end to end

def test_a_card_set_to_rubyx_gets_points_and_benefits(client, icici_clean, monkeypatch):  # noqa: F811
    upload(client, monkeypatch, {"multi.pdf": multi()})
    card = next(c for c in client.get(f"{API}/cards").json() if c["numbers"] == ["4005"])
    body = {"name": "ICICI Rubyx", "profile": "icici_rubyx", "rates": {}, "statement_day": 10, "grace_days": 20,
            "pay_buffer_days": 1, "float_rate": 7}
    assert client.put(f"{API}/cards/{card['id']}", json=body).status_code == 200
    d = client.get(f"{API}/cards/dashboard", params={"card_id": card["id"]}).json()
    assert [c["id"] for c in d["profile"]["classes"]] == ["international", "domestic", "utility", "excluded"]
    assert d["profile"]["point_value"] == 0.25 and d["profile"]["rewards"] is True
    dom = d["by_class"]["domestic"]
    assert dom["spend"] == 2400.0 and dom["cashback"] == 12.0 and dom["points"] == 48, "2,400 at 2 points per Rs 100 = 48 points"
    assert d["benefits"]["kind"] == "rubyx" and d["benefits"]["milestone"]["threshold"] == 300_000


def test_other_schemes_have_no_benefits_panel(client, icici_clean, monkeypatch):  # noqa: F811
    upload(client, monkeypatch, {"multi.pdf": multi()})
    card = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank")
    assert client.get(f"{API}/cards/dashboard", params={"card_id": card["id"]}).json()["benefits"] is None


def test_migration_seven_added_the_currency_column(seeded_db):
    db = database.get_db()
    try:
        assert "ccy" in {r[1] for r in db.execute("PRAGMA table_info(card_txns)")}
    finally:
        db.close()


# ------------------------------------------------------------------ Sapphiro: same earn rates, different benefits
# icici.bank.in: 4,000 points at Rs 4 lakh and 2,000 per further lakh up to 20,000 a year; 4 domestic lounge
# visits a quarter on Rs 75,000 or more in a calendar quarter; 2 international visits a year.

@pytest.mark.parametrize("spend,points", [
    (0, 0), (399_999, 0), (400_000, 4000), (499_999, 4000), (500_000, 6000), (900_000, 14_000),
    (1_200_000, 20_000), (5_000_000, 20_000),                       # capped at 20,000 a year
])
def test_sapphiro_milestone_points(spend, points):
    assert cards.milestone_points(spend, cards.SAPPHIRO_TERMS) == points


def test_the_two_schemes_do_not_share_a_milestone():
    assert cards.milestone_points(350_000, cards.RUBYX_TERMS) == 3000 and cards.milestone_points(350_000, cards.SAPPHIRO_TERMS) == 0


def test_sapphiro_earns_at_the_same_published_rates_as_rubyx():
    assert cards.PROFILES["icici_sapphiro"]["rates"] == cards.PROFILES["icici_rubyx"]["rates"]
    assert cards.PROFILES["icici_sapphiro"]["emi_earns"] is False


def test_sapphiro_lounge_counts_the_same_quarter_and_75000_exactly_qualifies():
    rows = [live(date(2025, 1, 15), 75_000), live(date(2025, 4, 15), 74_999)]
    q = {x["quarter"]: x for x in cards.card_benefits(rows, [], date(2025, 6, 1), 0.25, cards.SAPPHIRO_TERMS)["lounge"]["quarters"]}
    assert q["2025 Q1"]["entitled"] is True, "'75,000 or more' includes 75,000"
    assert q["2025 Q2"]["entitled"] is False
    assert q["2025 Q1"]["earns_next"] is False, "no next-quarter carry-over is claimed for Sapphiro"


def test_rubyx_and_sapphiro_lounge_differ_on_the_threshold_and_the_quarter():
    rows = [live(date(2025, 1, 15), 75_000), live(date(2025, 4, 15), 10_000)]
    rb_q = {x["quarter"]: x for x in cards.card_benefits(rows, [], date(2025, 6, 1), 0.25, cards.RUBYX_TERMS)["lounge"]["quarters"]}
    assert rb_q["2025 Q1"]["earns_next"] is False, "Rubyx needs MORE than 75,000"
    assert cards.card_benefits(rows, [], date(2025, 6, 1), 0.25, cards.SAPPHIRO_TERMS)["lounge"]["visits"] == 4


def test_a_card_set_to_sapphiro_gets_its_own_benefits(client, icici_clean, monkeypatch):  # noqa: F811
    upload(client, monkeypatch, {"multi.pdf": multi()})
    card = next(c for c in client.get(f"{API}/cards").json() if c["numbers"] == ["4005"])
    body = {"name": "ICICI Sapphiro", "profile": "icici_sapphiro", "rates": {}, "statement_day": 10, "grace_days": 20,
            "pay_buffer_days": 1, "float_rate": 7}
    assert client.put(f"{API}/cards/{card['id']}", json=body).status_code == 200
    b = client.get(f"{API}/cards/dashboard", params={"card_id": card["id"]}).json()["benefits"]
    assert b["kind"] == "sapphiro" and b["name"] == "Sapphiro"
    assert b["milestone"]["threshold"] == 400_000 and b["milestone"]["cap"] == 20_000 and b["lounge"]["visits"] == 4
