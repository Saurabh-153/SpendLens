"""Goal kinds and the monthly set-aside: large goals go to the corpus simulation, small goals and recurring expenses
(school fees, the trip home) to a steady set-aside, with planned vs spent for recurring expenses linked to a category."""
import itertools
from datetime import date

import portfolio as pf

API = "/spendlens/api"
ALL = ["expense", "holdings", "ledger", "cards"]
_n = itertools.count(1)


def months_ahead(k, today=None):
    t = today or date.today()
    i = t.year * 12 + t.month - 1 + k
    return i // 12, i % 12 + 1


# ---------------------------------------------------------------- occurrences
def test_recurring_occurrences_rise_yearly_and_stop_at_end_year():
    fee = {"kind": "recurring", "target_amount": 100000, "target_year": 2026, "target_month": 4,
           "every_months": 12, "escalation_pct": 10, "end_year": 2028}
    got = pf.occurrences(fee, pf._mi(2020, 1), pf._mi(2035, 12))
    assert [(pf._ym(i), a) for i, a in got] == [("2026-04", 100000), ("2027-04", 110000), ("2028-04", 121000)]


def test_recurring_that_started_in_the_past_keeps_its_rhythm():
    trip = {"kind": "recurring", "target_amount": 60000, "target_year": 2024, "target_month": 11, "every_months": 6}
    got = pf.occurrences(trip, pf._mi(2026, 10), pf._mi(2027, 6))
    assert [pf._ym(i) for i, _ in got] == ["2026-11", "2027-05"], "every 6 months from Nov 2024, not from today"
    assert all(a == 60000 for _, a in got), "no yearly rise set"


def test_one_off_goal_defaults_to_june_and_appears_once():
    g = {"kind": "small", "target_amount": 5000, "target_year": 2027, "target_month": None}
    assert pf.occurrences(g, pf._mi(2027, 1), pf._mi(2027, 12)) == [(pf._mi(2027, 6), 5000)]
    assert pf.occurrences(g, pf._mi(2028, 1), pf._mi(2028, 12)) == []


def test_default_kind_follows_the_five_lakh_cut():
    assert pf.default_kind(499999) == "small" and pf.default_kind(500000) == "large"


# ---------------------------------------------------------------- API
def test_goal_kinds_validation_and_defaults(make_user):
    a, _ = make_user(modules=ALL)
    small = a.post(f"{API}/portfolio/goals", json={"name": "Laptop", "target_amount": 150000, "target_year": 2030}).json()
    large = a.post(f"{API}/portfolio/goals", json={"name": "Car", "target_amount": 1200000, "target_year": 2030}).json()
    goals = {g["id"]: g for g in a.get(f"{API}/portfolio/plan").json()["goals"]}
    assert goals[small["id"]]["kind"] == "small" and goals[large["id"]]["kind"] == "large"
    assert a.post(f"{API}/portfolio/goals", json={"name": "X", "target_amount": 1, "target_year": 2030, "kind": "huge"}).status_code == 400
    assert a.post(f"{API}/portfolio/goals", json={"name": "X", "target_amount": 1, "target_year": 2030, "target_month": 13}).status_code == 400
    assert a.post(f"{API}/portfolio/goals", json={"name": "X", "target_amount": 1, "target_year": 2030, "kind": "recurring",
                                                  "end_year": 2029}).status_code == 400
    # recurring fields are dropped for a one-off goal
    a.put(f"{API}/portfolio/goals/{small['id']}", json={"name": "Laptop", "target_amount": 150000, "target_year": 2030,
                                                       "kind": "small", "escalation_pct": 9, "end_year": 2040})
    g = next(x for x in a.get(f"{API}/portfolio/plan").json()["goals"] if x["id"] == small["id"])
    assert g["escalation_pct"] == 0 and g["end_year"] is None


def test_large_goals_only_in_simulation_and_set_aside_covers_the_rest(make_user):
    a, _ = make_user(modules=ALL)
    cat = a.post(f"{API}/categories", json={"name": f"ZZ Travel {next(_n)}", "start_month": "2020-01"}).json()
    sub = a.post(f"{API}/subcategories", json={"category_id": cat["id"], "name": "Flights"}).json()
    today = date.today()
    a.post(f"{API}/expenses", json={"category_id": cat["id"], "subcategory_id": sub["id"], "date": today.isoformat(), "amount": 54000})
    a.post(f"{API}/expenses", json={"category_id": cat["id"], "date": today.isoformat(), "amount": 999})  # no sub-category: not counted
    y1, m1 = months_ahead(1)
    y6, m6 = months_ahead(6)
    a.post(f"{API}/portfolio/goals", json={"name": "Trip home", "target_amount": 60000, "target_year": y1, "target_month": m1,
                                           "kind": "recurring", "every_months": 12, "escalation_pct": 10,
                                           "category_id": cat["id"], "subcategory_id": sub["id"]})
    a.post(f"{API}/portfolio/goals", json={"name": "iPhone", "target_amount": 120000, "target_year": y6, "target_month": m6})
    k = a.get(f"{API}/portfolio/kpis").json()
    c = k["commitments"]
    assert {"set_aside", "top_up", "surplus", "payments", "small", "recurring", "months", "start"} <= set(c)
    assert c["set_aside"] == 25000, "60000/12 for the trip + 120000/6 for the phone"
    assert c["top_up"] == 35000, "the trip is due next month, before the pot has built up: 60000 - 25000"
    trip = c["recurring"][0]
    assert trip["next"] == {"month": f"{y1:04d}-{m1:02d}", "amount": 60000}
    assert trip["spent"] == 54000 and trip["link"].endswith("› Flights")
    assert trip["yearly"][0]["amount"] in (60000, 66000)
    assert [p["amount"] for p in c["payments"] if p["kind"] == "recurring"] == [60000, 66000], "the second year rises 10%"
    assert c["small"][0]["per_month"] == 20000 and c["small"][0]["months_left"] == 6
    if k["forecast"]:
        assert all(g["kind"] == "large" for g in k["forecast"]["goals"])


def test_a_goal_cannot_link_another_users_category(make_user):
    a, _ = make_user(modules=ALL)
    b, _ = make_user(modules=ALL)
    cat = a.post(f"{API}/categories", json={"name": f"ZZ A only {next(_n)}", "start_month": "2020-01"}).json()
    sub = a.post(f"{API}/subcategories", json={"category_id": cat["id"], "name": "Fees"}).json()
    body = {"name": "School fee", "target_amount": 120000, "target_year": 2026, "kind": "recurring", "category_id": cat["id"]}
    assert b.post(f"{API}/portfolio/goals", json=body).status_code == 404
    mine = b.post(f"{API}/categories", json={"name": f"ZZ B own {next(_n)}", "start_month": "2020-01"}).json()
    assert b.post(f"{API}/portfolio/goals", json={**body, "category_id": mine["id"], "subcategory_id": sub["id"]}).status_code == 404, \
        "a sub-category must belong to the linked category"
    assert b.post(f"{API}/portfolio/goals", json={**body, "category_id": mine["id"]}).status_code == 201
    assert all(g["name"] != "School fee" for g in a.get(f"{API}/portfolio/plan").json()["goals"])


def test_goals_and_their_spending_stay_private(make_user):
    from db.engine import SessionLocal
    from db.models import PortfolioGoal
    a, ua = make_user(modules=ALL)
    b, ub = make_user(modules=ALL)
    cat = a.post(f"{API}/categories", json={"name": f"ZZ Fees {next(_n)}", "start_month": "2020-01"}).json()
    a.post(f"{API}/expenses", json={"category_id": cat["id"], "date": date.today().isoformat(), "amount": 4321})
    y1, m1 = months_ahead(1)
    fee = a.post(f"{API}/portfolio/goals", json={"name": "A fee", "target_amount": 50000, "target_year": y1, "target_month": m1,
                                                 "kind": "recurring", "category_id": cat["id"]}).json()
    # B's own goal cannot be re-pointed at A's category, and B cannot change or delete A's goal
    mine = b.post(f"{API}/portfolio/goals", json={"name": "B fee", "target_amount": 1000, "target_year": y1, "kind": "recurring"}).json()
    assert b.put(f"{API}/portfolio/goals/{mine['id']}", json={"name": "B fee", "target_amount": 1000, "target_year": y1,
                                                              "kind": "recurring", "category_id": cat["id"]}).status_code == 404
    b.put(f"{API}/portfolio/goals/{fee['id']}", json={"name": "hijacked", "target_amount": 1, "target_year": 2030})
    b.delete(f"{API}/portfolio/goals/{fee['id']}")
    assert any(g["id"] == fee["id"] and g["name"] == "A fee" for g in a.get(f"{API}/portfolio/plan").json()["goals"])
    # A's plan and spending never show up in B's commitments
    cb = b.get(f"{API}/portfolio/kpis").json()["commitments"]
    assert [r["name"] for r in cb["recurring"]] == ["B fee"] and all(p["name"] != "A fee" for p in cb["payments"])
    # even a row written behind the route's back with A's category id reads no link and no spending for B
    with SessionLocal() as s:
        s.add(PortfolioGoal(user_id=ub["id"], name="Smuggled", target_amount=1000, target_year=y1, kind="recurring", category_id=cat["id"]))
        s.commit()
    smuggled = next(r for r in b.get(f"{API}/portfolio/kpis").json()["commitments"]["recurring"] if r["name"] == "Smuggled")
    assert smuggled["link"] is None and smuggled["spent"] is None
    assert next(r for r in a.get(f"{API}/portfolio/kpis").json()["commitments"]["recurring"] if r["name"] == "A fee")["spent"] == 4321


# ---------------------------------------------------------------- risk & safety inputs
def test_liquidity_buckets_and_ranked_positions():
    held = [{"name": "Cash", "asset_type": "CASH", "present": 100}, {"name": "Infy", "asset_type": "EQ", "present": 300},
            {"name": "Fund (Folio 1)", "asset_type": "MF", "present": 200}, {"name": "Fund (Folio 2)", "asset_type": "MF", "present": 100},
            {"name": "FD", "asset_type": "FD", "present": 150}, {"name": "EPF", "asset_type": "PF", "present": 150}]
    assert pf.liquidity(held) == {"instant": 100, "days": 600, "fixed": 150, "locked": 150}
    ranked = pf.concentration(held)["ranked"]
    assert ranked[0]["name"] in ("Infy", "Fund") and ranked[0]["pct"] == 30.0, "two folios of one fund are one position"
    assert abs(sum(r["pct"] for r in ranked) - 100) < 0.5
