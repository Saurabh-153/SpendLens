"""The SIP-mix engine's maths.

This is the part of the app that gives advice, so it gets real invariants rather than
shape checks. These are the acceptance tests from the roadmap: the mix at the reach
month equals the target, the forecast equals a brute-force loop, and an exposure that
is already over target is held at zero instead of going negative.
"""
from datetime import date

import portfolio as pf

TODAY = date(2026, 1, 1)


def plan(targets=None, returns=None, reach_years=5, years=15, stepup=0):
    return {"targets": targets or dict(pf.DEFAULT_MIX_TARGETS),
            "returns": returns or dict(pf.DEFAULT_MIX_RETURNS),
            "years": years, "reach_years": reach_years, "stepup": stepup}


def holding(name, exposure, present, sip=0.0, hid=1):
    return {"id": hid, "name": name, "exposure": exposure, "asset_type": "MF",
            "ticker": "", "grp": "Test", "present": float(present), "sip_amount": float(sip)}


def test_sip_split_by_exposure():
    d = pf.mix_summary([holding("E", "Equity", 100, 10000, 1),
                        holding("G", "Gold", 100, 2000, 2),
                        holding("D", "Debt", 100, 8000, 3)], plan(), TODAY)
    assert d["sip"]["total"] == 20000
    assert d["sip"]["by"]["Equity"]["amt"] == 10000
    assert d["sip"]["by"]["Equity"]["pct"] == 50.0


def test_cash_counts_as_debt():
    d = pf.mix_summary([holding("C", "Cash", 500), holding("D", "Debt", 500)], plan(), TODAY)
    assert d["current"]["value"]["Debt"] == 1000
    assert d["current"]["pct"]["Debt"] == 100


def test_already_on_target_reaches_immediately():
    held = [holding("E", "Equity", 600, 1000, 1), holding("G", "Gold", 100, 100, 2),
            holding("D", "Debt", 300, 500, 3)]
    d = pf.mix_summary(held, plan(), TODAY)
    assert d["plan"]["reach_month"] == 0
    assert d["plan"]["reachable"] is True


def test_mix_equals_target_at_the_reach_month():
    """The whole point of the feature: follow the suggested split and the mix lands on target."""
    held = [holding("E", "Equity", 100000, 5000, 1), holding("D", "Debt", 900000, 45000, 2)]
    d = pf.mix_summary(held, plan(reach_years=10), TODAY)
    reach = d["plan"]["reach_month"]
    assert reach, "an all-Debt portfolio with SIPs must be reachable"
    at_reach = next(p for p in d["path"] if p["m"] == reach)
    for e, want in d["targets"].items():
        assert abs(at_reach["rec"][e] - want) < 0.1, f"{e} is {at_reach['rec'][e]}, target {want}"


def test_over_target_exposure_is_held_at_zero_not_negative():
    """Nothing is sold, so an exposure that cannot come down in time gets no new SIP.

    Note the SIP must be small against the corpus for this to bite. With a large SIP,
    starving Equity would push it *below* target, so the engine correctly still gives it
    a share — that case is `test_a_large_sip_still_feeds_an_over_target_exposure`.
    """
    held = [holding("E", "Equity", 5_000_000, 5000, 1), holding("D", "Debt", 1000, 0, 2)]
    d = pf.mix_summary(held, plan(reach_years=2), TODAY)
    rec = d["plan"]["recommended"]
    assert rec["Equity"]["amt"] == 0, "an over-target exposure should receive nothing"
    assert all(r["amt"] >= 0 for r in rec.values())
    assert abs(sum(r["amt"] for r in rec.values()) - d["sip"]["total"]) < 2


def test_a_large_sip_still_feeds_an_over_target_exposure():
    """Guards against over-correcting: starving Equity here would undershoot the target."""
    held = [holding("E", "Equity", 1_000_000, 50000, 1), holding("D", "Debt", 1000, 0, 2)]
    d = pf.mix_summary(held, plan(reach_years=5), TODAY)
    rec = d["plan"]["recommended"]
    assert rec["Equity"]["amt"] > 0
    reach = d["plan"]["reach_month"]
    at_reach = next(p for p in d["path"] if p["m"] == reach)
    assert abs(at_reach["rec"]["Equity"] - d["targets"]["Equity"]) < 0.1


def test_unreachable_portfolio_is_reported_not_faked():
    """Equity so far over target that SIPs alone cannot fix it must say so."""
    held = [holding("E", "Equity", 10_000_000, 1000, 1)]
    d = pf.mix_summary(held, plan(reach_years=1), TODAY)
    assert d["plan"]["reachable"] is False
    assert d["plan"]["reach_month"] is None


def test_suggested_split_spends_the_whole_sip_and_nets_to_zero():
    held = [holding("E", "Equity", 200000, 10000, 1), holding("G", "Gold", 50000, 1000, 2),
            holding("D", "Debt", 750000, 19000, 3)]
    d = pf.mix_summary(held, plan(), TODAY)
    rec = d["plan"]["recommended"]
    assert abs(sum(r["amt"] for r in rec.values()) - 30000) < 2
    assert abs(sum(r["delta"] for r in rec.values())) < 2


def test_forecast_matches_a_brute_force_loop():
    """Independent re-derivation of the growth maths: monthly rate, SIP at month end."""
    start, sip, years = 500000.0, 10000.0, 1
    held = [holding("E", "Equity", start, sip, 1)]
    p = plan(targets={"Equity": 100, "Gold": 0, "Debt": 0},
             returns={"Equity": 12, "Gold": 8, "Debt": 7}, years=years, reach_years=1)
    d = pf.mix_summary(held, p, TODAY)

    rm = (1 + 0.12) ** (1 / 12) - 1
    bal = start
    for _ in range(12):
        bal = bal * (1 + rm) + sip
    year_one = next(f for f in d["forecast"] if f["months"] == 12)
    assert abs(year_one["total"] - bal) < 2, f"engine {year_one['total']} vs loop {bal:.0f}"


def test_stepup_raises_the_sip_every_twelve_months():
    held = [holding("E", "Equity", 100000, 10000, 1)]
    d = pf.mix_summary(held, plan(stepup=10, reach_years=3), TODAY)
    sips = {p["m"]: p["sip_rec"] for p in d["path"] if p["m"] in (1, 12, 13)}
    first = sum(sips[1].values())
    assert abs(sum(sips[12].values()) - first) < 1, "the step-up must land in month 13, not 12"
    assert abs(sum(sips[13].values()) - first * 1.1) < first * 0.01


def test_empty_portfolio_does_not_crash():
    d = pf.mix_summary([], plan(), TODAY)
    assert d["plan"] is None and d["path"] == [] and d["forecast"] == []
