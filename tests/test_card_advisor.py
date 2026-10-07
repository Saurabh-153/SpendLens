"""Which card for what: purposes, rates, and that closed cards are never recommended."""
import card_advisor as A

API = "/spendlens/api"


def test_purposes_come_from_the_merchant_not_the_card():
    assert A.purpose_of("Amazon", "AMAZON PAY INDIA MUMBAI") == "amazon"
    assert A.purpose_of("Swiggy", "SWIGGY BANGALORE") == "food"
    assert A.purpose_of("Bigbasket", "BIGBASKET BANGALORE") == "tata"
    assert A.purpose_of("X", "UPI-SOME SHOP-1234") == "upi", "UPI is its own purpose"
    assert A.purpose_of("Shop", "SOME SHOP", "Miscellaneous · Other") == "instore"
    assert A.purpose_of("Shop", "SOME SHOP", "Business Services · Insurance Services") == "insurance"


def test_every_scheme_has_a_rate_for_every_purpose():
    for profile, t in A.TERMS.items():
        assert set(t) == set(A.PURPOSE_IDS), profile


def test_a_named_merchant_can_beat_its_purpose_rate():
    assert A.rate_for("amex_smartearn", "food", "zomato") == 5.0
    assert A.rate_for("amex_smartearn", "food", "swiggy") == 0.5


def test_the_advice_shape_and_arithmetic(client, seeded_db):
    d = client.get(f"{API}/cards/advice").json()
    assert {p["id"] for p in d["purposes"]} == set(A.PURPOSE_IDS)
    t = d["totals"]
    assert t["best_12m"] >= t["earned_12m"] - 0.01, "the best possible is never below what was earned"
    assert abs(t["missed_12m"] - sum(p["missed_12m"] for p in d["purposes"])) < 0.05


def test_a_closed_card_is_never_recommended(client, seeded_db):
    cards = client.get(f"{API}/cards").json()
    sbi = next(c for c in cards if c["profile"] == "sbi_cashback")
    before = client.get(f"{API}/cards/advice").json()
    assert next(p for p in before["purposes"] if p["id"] == "amazon")["best"]["name"] == sbi["name"]
    client.patch(f"{API}/cards/{sbi['id']}", json={"status": "closed"})
    try:
        after = client.get(f"{API}/cards/advice").json()
    finally:
        client.patch(f"{API}/cards/{sbi['id']}", json={"status": "active"})   # the DB is shared by the whole session
    for p in after["purposes"]:
        assert not p["best"] or p["best"]["card_id"] != sbi["id"]
    assert sbi["name"] in after["closed"]
