"""Two users with every module on must not see or change each other's data (db/scope.py + the cards SQL)."""
import itertools

import pytest

API = "/spendlens/api"
ALL = ["expense", "holdings", "ledger", "cards"]
_n = itertools.count(1)


@pytest.fixture
def pair(make_user):
    """(client A, user A, client B, user B), both with every module."""
    a, ua = make_user(modules=ALL)
    b, ub = make_user(modules=ALL)
    return a, ua, b, ub


def names(rows, key="name"):
    return {r[key] for r in rows}


def test_new_user_starts_with_defaults_and_no_data(pair):
    a, ua, b, ub = pair
    cats = b.get(f"{API}/categories").json()
    assert len(cats) >= 15, "default categories were seeded"
    assert b.get(f"{API}/holdings").json() == []
    assert b.get(f"{API}/equity/summary").json()["stocks"] == []
    assert b.get(f"{API}/cards").json() == []
    assert b.get(f"{API}/trackers").json() == []
    assert b.get(f"{API}/portfolio/plan").json()["goals"] == [], "the owner's personal goals are not handed to new users"
    assert b.get(f"{API}/budget").status_code == 200


def test_categories_and_expenses_are_private(pair):
    a, ua, b, ub = pair
    cat = a.post(f"{API}/categories", json={"name": f"ZZ A only {next(_n)}", "start_month": "2020-01"}).json()
    e = a.post(f"{API}/expenses", json={"category_id": cat["id"], "date": "2021-03-04", "amount": 123}).json()
    assert cat["name"] in names(a.get(f"{API}/categories").json())
    assert cat["name"] not in names(b.get(f"{API}/categories").json())
    # B cannot use A's category, or touch A's expense by id
    assert b.post(f"{API}/expenses", json={"category_id": cat["id"], "date": "2021-03-04", "amount": 1}).status_code in (400, 404, 409)
    b.delete(f"{API}/expenses/{e['id']}")   # answers ok whether or not it matched; what matters is that A's row survives
    assert any(x["id"] == e["id"] for x in (lambda r: r if isinstance(r, list) else r.get("expenses", []))(a.get(f"{API}/expenses", params={"month": "2021-03"}).json()))
    assert b.put(f"{API}/expenses/{e['id']}", json={"category_id": cat["id"], "date": "2021-03-04", "amount": 1}).status_code in (400, 404)
    assert b.put(f"{API}/categories/{cat['id']}", json={"name": "hijacked"}).status_code == 404
    month = a.get(f"{API}/expenses", params={"month": "2021-03"}).json()
    assert any(x["amount"] == 123 for x in (month if isinstance(month, list) else month.get("expenses", [])))
    mine_b = b.get(f"{API}/expenses", params={"month": "2021-03"}).json()
    assert not any(x.get("amount") == 123 for x in (mine_b if isinstance(mine_b, list) else mine_b.get("expenses", [])))
    assert a.get(f"{API}/categories").json()  # A is unaffected by B's attempts


def test_a_body_cannot_name_another_users_id(pair):
    a, ua, b, ub = pair
    cat = a.post(f"{API}/categories", json={"name": f"ZZ own {next(_n)}", "start_month": "2020-01"}).json()
    a.post(f"{API}/expenses", json={"category_id": cat["id"], "date": "2021-05-05", "amount": 7, "user_id": ub["id"]})
    assert not any(x.get("amount") == 7 for x in (lambda r: r if isinstance(r, list) else r.get("expenses", []))(b.get(f"{API}/expenses", params={"month": "2021-05"}).json()))


def test_holdings_and_portfolio_are_private(pair):
    a, ua, b, ub = pair
    h = a.post(f"{API}/holdings", json={"name": f"ZZ Fund {next(_n)}", "asset_type": "EQ", "qty": 10, "buy_price": 100, "cmp": 120}).json()
    assert h["name"] in names(a.get(f"{API}/holdings").json())
    assert h["name"] not in names(b.get(f"{API}/holdings").json())
    b.delete(f"{API}/holdings/{h['id']}")
    assert h["name"] in names(a.get(f"{API}/holdings").json()), "B's delete did not remove A's holding"
    assert b.put(f"{API}/holdings/{h['id']}", json={"name": "x", "qty": 1, "buy_price": 1, "cmp": 1}).status_code in (404, 422)
    kpi_b = b.get(f"{API}/portfolio/kpis").json()
    assert not kpi_b or kpi_b.get("present", 0) in (0, None) or "present" not in kpi_b
    # holding groups: the same name is allowed for two users
    assert a.post(f"{API}/holding-groups", json={"name": "ZZ Shared Name"}).status_code == 201
    assert b.post(f"{API}/holding-groups", json={"name": "ZZ Shared Name"}).status_code == 201
    # holding-columns layout is per user
    a.put(f"{API}/holding-columns", json={"order": ["a"], "hidden": ["b"]})
    assert b.get(f"{API}/holding-columns").json() == {"order": [], "hidden": []}


def test_reminders_trackers_and_vacations_are_private(pair):
    a, ua, b, ub = pair
    cats = a.get(f"{API}/reminder-categories").json()
    assert cats, "a new user has the calendar categories"
    rem = a.post(f"{API}/reminders", json={"category_id": cats[0]["id"], "name": f"ZZ rent {next(_n)}", "day": 5, "amount": 10}).json()
    tr = a.post(f"{API}/trackers", json={"name": f"ZZ gym {next(_n)}"}).json()
    vac = a.post(f"{API}/vacations", json={"name": f"ZZ trip {next(_n)}", "start_date": "2021-04-01", "end_date": "2021-04-03"}).json()
    assert rem["name"] not in names(b.get(f"{API}/reminders").json())
    assert tr["name"] not in names(b.get(f"{API}/trackers").json())
    assert vac["name"] not in names(b.get(f"{API}/vacations").json())
    assert b.delete(f"{API}/reminders/{rem['id']}").status_code == 404
    assert b.put(f"{API}/trackers/{tr['id']}/days/2021-04-02", json={"done": True}).status_code == 404
    assert b.delete(f"{API}/vacations/{vac['id']}").status_code == 404
    # the calendar feed and month view only carry the caller's items
    assert rem["name"] not in b.get(f"{API}/reminders/calendar", params={"month": "2021-04"}).text


def test_cards_are_private(pair):
    import cards
    from db.engine import SessionLocal
    a, ua, b, ub = pair
    with SessionLocal() as s:
        s.info["user_id"] = ua["id"]
        card = cards._insert_card(s, {"issuer": "HDFC", "last4": "9876", "name": f"ZZ card {next(_n)}"})
        s.commit()
    assert card["user_id"] == ua["id"]
    assert card["name"] in names(a.get(f"{API}/cards").json())
    assert b.get(f"{API}/cards").json() == []
    for path in (f"/cards/{card['id']}/txns", f"/cards/{card['id']}/perks"):
        assert b.get(f"{API}{path}").status_code in (404, 200) and b.get(f"{API}{path}").json() in ([], {}, None) or b.get(f"{API}{path}").status_code == 404
    assert b.put(f"{API}/cards/{card['id']}", json={"name": "hijacked"}).status_code in (404, 400, 422)
    # A's card was not renamed
    assert card["name"] in names(a.get(f"{API}/cards").json())
    perks = a.get(f"{API}/cards/{card['id']}/perks")
    assert perks.status_code == 200


def test_scheduler_style_unscoped_work_still_sees_everyone(pair):
    """An unscoped session (price scheduler, start-up) is not filtered - it is the code's job to loop users."""
    from db.engine import SessionLocal
    from db.models import Category
    a, ua, b, ub = pair
    with SessionLocal() as s:
        owners = {c.user_id for c in s.query(Category)}
    assert {ua["id"], ub["id"]} <= owners


def test_mf_factsheet_data_is_private(pair):
    """mf_sources / mf_fund_months / mf_holdings: one user's imported factsheets never reach another."""
    import mf
    from db.engine import SessionLocal
    a, ua, b, ub = pair
    s = SessionLocal()
    s.info["user_id"] = ua["id"]
    mf.import_payload(s, {"month": "2026-10", "source": "ZZ.pdf", "funds": [
        {"scheme": f"ZZ Iso Fund {next(_n)}", "ter_pct": 0.5, "holdings": [{"name": "Iso Co", "pct": 99}]}]})
    s.commit()
    s.close()
    assert a.get(f"{API}/mf/analysis").json()["has_data"]
    got = b.get(f"{API}/mf/analysis").json()
    assert not got["has_data"] and got["funds"] == [] and got["sources"] == [] and got["coverage"] == []



def test_mf_same_file_and_fund_imported_by_two_users_stay_separate(pair):
    """Both users import the same (month, source) and the same scheme: each keeps its own rows and holdings."""
    import mf
    from db.engine import SessionLocal
    from db.models import MfFundMonth, MfHolding, MfSource
    a, ua, b, ub = pair
    scheme = f"ZZ Shared Scheme {next(_n)}"

    def load(uid, ter, stock):
        s = SessionLocal()
        s.info["user_id"] = uid
        mf.import_payload(s, {"month": "2026-10", "source": "Same.pdf", "funds": [
            {"scheme": scheme, "ter_pct": ter, "holdings": [{"name": stock, "isin": "", "pct": 99}]}]})
        s.commit()
        s.close()
    load(ua["id"], 0.5, "A Co")
    load(ub["id"], 0.9, "B Co")
    load(ub["id"], 0.95, "B Co 2")   # B re-imports: replaces only B's holdings
    s = SessionLocal()   # unscoped: see both users' rows
    try:
        rows = {r.user_id: r for r in s.query(MfFundMonth).filter(MfFundMonth.scheme == scheme)}
        assert set(rows) == {ua["id"], ub["id"]} and rows[ua["id"]].ter_pct == 0.5 and rows[ub["id"]].ter_pct == 0.95
        held = {r.user_id: sorted(h.name for h in s.query(MfHolding).filter(MfHolding.fund_month_id == r.id)) for r in rows.values()}
        assert held == {ua["id"]: ["A Co"], ub["id"]: ["B Co 2"]}
        assert s.query(MfSource).filter(MfSource.file_name == "Same.pdf", MfSource.user_id.in_([ua["id"], ub["id"]])).count() == 2
    finally:
        s.close()


def test_mf_reports_are_private(pair):
    """mf_reports (Morningstar cross-check reports): stamped with the importing user, invisible to the other."""
    import mf
    from db.engine import SessionLocal
    from db.models import MfReport
    a, ua, b, ub = pair
    name = f"ZZ Iso Report Fund {next(_n)} Direct Growth"
    s = SessionLocal()
    s.info["user_id"] = ua["id"]
    mf.import_payload(s, {"month": "2026-09", "source": "IsoR.pdf", "funds": [{"scheme": name.replace(" Direct Growth", ""), "plan": "Direct"}]})
    mf.import_report(s, {"fund": name, "report_date": "2026-11-08", "portfolio_date": "2026-09-30"}, "ms.pdf", "sha", b"%PDF-1.4 iso")
    s.commit()
    s.close()
    s = SessionLocal()
    s.info["user_id"] = ub["id"]
    try:
        assert s.query(MfReport).filter(MfReport.scheme == name).count() == 0
    finally:
        s.close()
    got = [f for f in a.get(f"{API}/mf/analysis").json()["funds"] if f["name"] == name.replace(" Direct Growth", "")]
    assert got and len(got[0]["reports"]) == 1
    assert all(not f["reports"] for f in b.get(f"{API}/mf/analysis").json()["funds"])
    rid = got[0]["reports"][0]["id"]
    assert a.get(f"{API}/mf/reports/{rid}/pdf").status_code == 200
    assert b.get(f"{API}/mf/reports/{rid}/pdf").status_code == 404   # the other user can't fetch it by id
