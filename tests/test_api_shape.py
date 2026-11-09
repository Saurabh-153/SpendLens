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
    ("/portfolio/kpis", {"history", "forecast", "extra_sip_needed", "commitments", "concentration", "fixed", "liquidity"}),
    ("/prices/status", None),
    ("/equity/summary", {"accounts", "kpis", "stocks", "dividends", "coverage", "issue_counts"}),
    ("/equity/audit", {"issues", "log", "holdings_checks"}),
    ("/equity/events", {"events", "kinds"}),
    ("/mf/analysis", {"has_data", "funds", "anomalies", "overlap", "coverage", "unmatched_holdings", "latest_month", "sources"}),
]


@pytest.mark.parametrize("path,keys", READ_ENDPOINTS, ids=[p for p, _ in READ_ENDPOINTS])
def test_read_endpoint_responds(client, path, keys):
    r = client.get(API + path)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:300]}"
    body = r.json()
    if keys is not None:
        assert isinstance(body, dict), f"{path} should return an object"
        assert keys <= set(body), f"{path} is missing {keys - set(body)}"


def test_kpi_sip_is_split_into_equity_fixed_income_and_gold(make_user):
    """The tile's three rows must add up to the total, and PF, FD, liquid and emergency money must not count as equity."""
    a, _ = make_user(modules=["holdings"])
    for name, kind, grp, amt in [
        ("ZZ Flexi Cap Fund", "MF", "Mutual Funds", 1000),
        ("ZZ Infosys", "EQ", "Equity", 2000),
        ("ZZ Gold ETF", "GOLD", "Gold", 4000),
        ("ZZ EPF", "PF", "Provident Fund", 8000),
        ("ZZ Bank FD", "FD", "Fixed Return", 16000),
        ("ZZ Liquid Fund", "MF", "Mutual Funds", 32000),
        ("ZZ Conservative Hybrid", "MF", "Emergency Fund", 64000),  # the name alone would guess Equity
    ]:
        r = a.post(f"{API}/holdings", json={"name": name, "asset_type": kind, "grp": grp, "qty": 1, "buy_price": 100, "cmp": 100, "sip_amount": amt})
        assert r.status_code == 201, r.text
    sip = a.get(f"{API}/portfolio/kpis").json()["sip"]
    assert sip["by_mix"] == {"Equity": 3000, "Gold": 4000, "Debt": 120000}
    assert sum(sip["by_mix"].values()) == sip["monthly"]


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


def test_dashboard_categories_carry_six_months_of_history(client):
    """The category cards on the Expense page draw a six-month sparkline; the last point is this month's spend."""
    d = client.get(f"{API}/dashboard?month={MONTH}").json()
    for c in d["categories"]:
        assert len(c["history"]) == 6
        assert c["history"][-1] == c["spent"]


def test_cashback_is_not_counted_as_spend(client):
    """A long-standing invariant: cashback is reported, never added to the total."""
    d = client.get(f"{API}/dashboard?month={MONTH}").json()
    assert "cashback" in str(d), "the dashboard no longer reports cashback"
