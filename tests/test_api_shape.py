"""Shape tests for every read endpoint.

These are deliberately about *shape*, not values: they answer "did a refactor quietly
drop a field the UI reads". The frontend's expectations live in `src/api.ts`, so when a
key here changes, that file changes with it.
"""
import pytest

API = "/spendlens/api"
MONTH = "2025-02"  # a month the seed data fills

# path -> keys the response must still carry (a list response is checked for its length only)
READ_ENDPOINTS = [
    ("/healthz", {"status"}),
    ("/categories", None),
    ("/budget", None),  # the salary / saving change history, newest last
    ("/subcategories", None),
    ("/subcategories/review", None),
    ("/expenses/months", None),
    (f"/expenses/monthly-grid?month={MONTH}", None),
    (f"/dashboard?month={MONTH}", None),
    ("/holding-groups", None),
    ("/holdings", None),
    ("/sip-log", None),
    ("/portfolio/plan", None),
    ("/portfolio/exposure", {"exposures", "total", "by_group", "tags"}),
    ("/portfolio/mix", {"targets", "returns", "current", "sip", "plan", "path", "forecast"}),
    ("/portfolio/kpis", None),
    ("/prices/status", None),
    ("/transactions", None),
    ("/ledger/summary", None),
]


@pytest.mark.parametrize("path,keys", READ_ENDPOINTS, ids=[p for p, _ in READ_ENDPOINTS])
def test_read_endpoint_responds(client, path, keys):
    r = client.get(API + path)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:300]}"
    body = r.json()
    if keys is not None:
        assert isinstance(body, dict), f"{path} should return an object"
        assert keys <= set(body), f"{path} is missing {keys - set(body)}"


def test_mix_targets_sum_to_100(client):
    targets = client.get(f"{API}/portfolio/mix").json()["targets"]
    assert set(targets) == {"Equity", "Gold", "Debt"}
    assert abs(sum(targets.values()) - 100) < 0.01


def test_mix_recommended_split_is_a_full_split(client):
    """The suggested SIP shares must account for every rupee, or the advice is wrong."""
    rec = client.get(f"{API}/portfolio/mix").json()["plan"]["recommended"]
    assert rec is not None, "no suggested split for a portfolio that has SIPs"
    assert set(rec) == {"Equity", "Gold", "Debt"}
    assert abs(sum(r["pct"] for r in rec.values()) - 100) < 0.5
    assert all(r["amt"] >= 0 for r in rec.values()), "a SIP cannot be negative"


def test_mix_sip_total_matches_the_holdings(client):
    """SIP by exposure must add up to the SIP actually set on the holdings."""
    d = client.get(f"{API}/portfolio/mix").json()
    assert abs(sum(d["sip"]["by"][e]["amt"] for e in d["sip"]["by"]) - d["sip"]["total"]) < 0.01
    rec = d["plan"]["recommended"]
    assert abs(sum(r["amt"] for r in rec.values()) - d["sip"]["total"]) < 2, \
        "the suggested split must spend the same total SIP, since nothing is sold"
    # delta is what moves, so it must net to zero
    assert abs(sum(r["delta"] for r in rec.values())) < 2


def test_exposure_shares_total_100(client):
    d = client.get(f"{API}/portfolio/exposure").json()
    if d["total"] <= 0:
        pytest.skip("no holdings in the seeded database")
    assert abs(sum(e["pct"] for e in d["exposures"]) - 100) < 0.5


def test_unknown_month_is_not_an_error(client):
    """The UI lets you page to any month; an empty one must come back empty, not 500."""
    r = client.get(f"{API}/expenses/monthly-grid?month=1999-01")
    assert r.status_code == 200


def test_cashback_is_not_counted_as_spend(client):
    """A long-standing invariant: cashback is reported, never added to the total."""
    d = client.get(f"{API}/dashboard?month={MONTH}").json()
    assert "cashback" in str(d), "the dashboard no longer reports cashback"
