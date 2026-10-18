"""Portfolio write paths on SQLAlchemy: holdings, SIPs, the ledger, price refresh and snapshots.

Every test cleans up the rows it adds, because the seeded database is shared by the whole suite.
"""
import json
from datetime import date

import pytest

API = "/spendlens/api"


def _month_back(today, n):
    m = today.year * 12 + today.month - 1 - n
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


@pytest.fixture
def session(seeded_db):
    from db.engine import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def cleanup(seeded_db):
    """Collects holding ids created by a test and deletes them with their SIP log and ledger rows."""
    ids = []
    yield ids
    from db.engine import SessionLocal
    from db.models import Holding
    from db.models.portfolio import LedgerTransaction, PriceHistory, SipLog
    s = SessionLocal()
    try:
        for model, col in ((SipLog, SipLog.holding_id), (LedgerTransaction, LedgerTransaction.holding_id),
                           (PriceHistory, PriceHistory.holding_id), (Holding, Holding.id)):
            s.query(model).filter(col.in_(ids)).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()


def _new_holding(client, cleanup, **kw):
    body = {"name": "ZZ Test Holding", "asset_type": "EQ", "qty": 10, "buy_price": 100, "cmp": 120, **kw}
    r = client.post(f"{API}/holdings", json=body)
    assert r.status_code == 201, r.text
    cleanup.append(r.json()["id"])
    return r.json()


# ---------------------------------------------------------------- holdings + SIP setup
def test_holding_crud_round_trip(client, cleanup):
    h = _new_holding(client, cleanup, sip_amount=1500, sip_day=1)
    assert (h["invested"], h["present"], h["pl"], h["pl_pct"]) == (1000.0, 1200.0, 200.0, 20.0)
    assert h["sip_day"] == 1 and h["sip_applied"] == date.today().strftime("%Y-%m"), "day 1 has passed: this month counts as applied"
    assert "sip_reminder" not in h

    upd = {**{k: h[k] for k in ("name", "ticker", "asset_type", "sector", "qty", "buy_price", "week52_low", "week52_high",
                                 "notes", "tags", "exposure", "grp", "maturity", "rate", "start_date", "compounding",
                                 "rd", "credits", "manual", "visible")},
           "cmp": 150, "sip_amount": 2000, "sip_day": 28}
    r = client.put(f"{API}/holdings/{h['id']}", json=upd)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["present"] == 1500.0 and out["sip_amount"] == 2000 and out["sip_day"] == 28
    assert out["sip_applied"] != "", "a new SIP day sets a fresh baseline month"

    assert any(x["id"] == h["id"] for x in client.get(f"{API}/holdings?type=EQ").json())
    assert client.delete(f"{API}/holdings/{h['id']}").json() == {"ok": True}
    assert not any(x["id"] == h["id"] for x in client.get(f"{API}/holdings").json())


def test_set_sip_endpoint_validates_and_404s(client, cleanup):
    h = _new_holding(client, cleanup)
    assert client.put(f"{API}/holdings/{h['id']}/sip", json={"sip_amount": -1, "sip_day": 3}).status_code == 400
    assert client.put(f"{API}/holdings/{h['id']}/sip", json={"sip_amount": 10, "sip_day": 32}).status_code == 400
    assert client.put(f"{API}/holdings/99999999/sip", json={"sip_amount": 10, "sip_day": 3}).status_code == 404
    assert client.put(f"{API}/holdings/{h['id']}/sip", json={"sip_amount": 500, "sip_day": 3}).json() == {"ok": True}


# ---------------------------------------------------------------- SIP catch-up
def test_due_sips_catch_up_once_per_month(client, cleanup, session):
    import sip
    from db.models import Holding
    from db.models.portfolio import LedgerTransaction, SipLog
    today = date.today()
    h = _new_holding(client, cleanup, name="ZZ PPF catch-up", asset_type="PF", qty=1, buy_price=10000, cmp=10000)
    row = session.get(Holding, h["id"])
    row.sip_amount, row.sip_day, row.sip_applied = 1000, 1, _month_back(today, 3)
    session.commit()

    assert sip.apply_due_sips(session, today) >= 3
    session.refresh(row)
    assert (row.qty, row.buy_price, row.cmp) == (1.0, 13000.0, 13000.0), "direct holdings add the amount to cost and value"
    assert row.sip_applied == today.strftime("%Y-%m")
    logs = session.query(SipLog).filter(SipLog.holding_id == h["id"]).order_by(SipLog.id).all()
    assert [l.month for l in logs] == [_month_back(today, n) for n in (2, 1, 0)]
    assert all(l.amount == 1000 and len(l.applied_at) == 19 for l in logs)
    txs = session.query(LedgerTransaction).filter(LedgerTransaction.holding_id == h["id"]).all()
    assert [(t.kind, t.source, t.applied, t.amount, t.qty, t.price) for t in txs] == [("BUY", "sip", 1, 1000, 0, 0)] * 3

    before = session.query(SipLog).count()
    sip.apply_due_sips(session, today)
    assert session.query(SipLog).count() == before, "a month is never applied twice"


def test_mf_sip_buys_units_at_nav(client, cleanup, session):
    import sip
    from db.models import Holding
    today = date.today()
    h = _new_holding(client, cleanup, name="ZZ MF units", asset_type="MF", qty=1, buy_price=5000, cmp=6000)
    row = session.get(Holding, h["id"])
    row.units, row.nav, row.sip_amount, row.sip_day, row.sip_applied = 100.0, 60.0, 600, 1, _month_back(today, 1)
    session.commit()
    sip.apply_due_sips(session, today)
    session.refresh(row)
    assert row.units == pytest.approx(110.0) and row.cmp == pytest.approx(6600.0) and row.buy_price == 5600


# ---------------------------------------------------------------- ledger
def test_ledger_buy_sell_apply_and_delete(client, cleanup):
    h = _new_holding(client, cleanup, name="ZZ Ledger EQ")
    buy = client.post(f"{API}/transactions", json={"holding_id": h["id"], "tx_date": "2025-06-10", "kind": "buy",
                                                  "qty": 10, "price": 140, "fees": 5, "apply": 1})
    assert buy.status_code == 201, buy.text
    held = next(x for x in client.get(f"{API}/holdings").json() if x["id"] == h["id"])
    assert held["qty"] == 20 and held["buy_price"] == pytest.approx((1000 + 1405) / 20) and held["cmp"] == 120

    too_many = client.post(f"{API}/transactions", json={"holding_id": h["id"], "tx_date": "2025-07-01", "kind": "SELL",
                                                       "qty": 50, "price": 150, "apply": 1})
    assert too_many.status_code == 400 and "only hold" in too_many.json()["detail"]
    held = next(x for x in client.get(f"{API}/holdings").json() if x["id"] == h["id"])
    assert held["qty"] == 20, "a rejected sale changes nothing"

    sell = client.post(f"{API}/transactions", json={"holding_id": h["id"], "tx_date": "2025-07-01", "kind": "SELL",
                                                   "qty": 5, "price": 150, "apply": 1})
    assert sell.status_code == 201
    rows = client.get(f"{API}/transactions?holding_id={h['id']}").json()
    assert rows["total"] == 2 and [r["kind"] for r in rows["rows"]] == ["SELL", "BUY"]
    assert rows["rows"][0]["fy"] == "FY2025-26" and rows["rows"][0]["realized"] == pytest.approx(750 - 5 * (2405 / 20))
    assert list(rows["rows"][0])[:4] == ["id", "holding_id", "name", "tx_date"], "row keys keep the table's column order"

    assert client.post(f"{API}/transactions", json={"tx_date": "2025-07-01", "kind": "BUY", "amount": 5}).status_code == 400
    assert client.post(f"{API}/transactions", json={"holding_id": 99999999, "tx_date": "2025-07-01", "kind": "BUY"}).status_code == 404

    summary = client.get(f"{API}/ledger/summary").json()
    assert any(x["id"] == h["id"] and x["covered"] for x in summary["xirr"]["holdings"])
    client.delete(f"{API}/transactions/{buy.json()['id']}")
    assert client.get(f"{API}/transactions?holding_id={h['id']}").json()["total"] == 1


# ---------------------------------------------------------------- prices
def test_price_refresh_with_stubbed_sources(client, cleanup, monkeypatch):
    import prices
    from db.engine import SessionLocal
    from db.models.portfolio import PriceHistory, PriceRun
    from routes.investing_routes import refresh_and_snapshot
    eq = _new_holding(client, cleanup, name="ZZ Priced EQ", ticker="ZZEQ")
    mf = _new_holding(client, cleanup, name="ZZ Priced MF", asset_type="MF", qty=1, buy_price=900, cmp=1000)
    bad = _new_holding(client, cleanup, name="ZZ Bad ticker", ticker="NOPE")
    for h, cfg in ((eq, {"ticker": "zzeq", "auto_price": 1}), (mf, {"scheme_code": "999", "units": 10, "auto_price": 1}),
                   (bad, {"ticker": "NOPE", "auto_price": 1})):
        assert client.put(f"{API}/prices/holding/{h['id']}", json=cfg).json() == {"ok": True}

    def quote(t):
        if t == "NOPE":
            raise RuntimeError("no such symbol")
        return {"price": 130.0, "low": 90.0, "high": 140.0, "date": "2026-01-02", "name": "ZZ"}
    monkeypatch.setattr(prices, "yahoo_quote", quote)
    monkeypatch.setattr(prices, "fetch_amfi", lambda *a, **k: {"999": {"name": "ZZ", "plan": "Direct", "option": "Growth",
                                                                       "nav": 110.0, "date": "2026-01-02"}})
    runs_before = SessionLocal().query(PriceRun).count()
    for _ in range(2):  # the second run on the same day replaces the day's price instead of duplicating it
        out = refresh_and_snapshot()
        assert out["updated"] >= 2 and any("ZZ Bad ticker" in e for e in out["errors"])

    by_id = {x["id"]: x for x in client.get(f"{API}/holdings").json()}
    assert (by_id[eq["id"]]["cmp"], by_id[eq["id"]]["week52_high"], by_id[eq["id"]]["price_note"]) == (130.0, 140.0, "")
    assert (by_id[mf["id"]]["nav"], by_id[mf["id"]]["cmp"], by_id[mf["id"]]["qty"]) == (110.0, 1100.0, 1)
    assert by_id[bad["id"]]["price_note"] == "no such symbol"
    s = SessionLocal()
    assert s.query(PriceHistory).filter(PriceHistory.holding_id.in_([eq["id"], mf["id"]])).count() == 2
    assert s.query(PriceRun).count() == runs_before + 2
    s.close()
    status = client.get(f"{API}/prices/status").json()
    assert status["runs"][0]["ok"] == 1 and list(status["runs"][0]) == ["id", "ran_at", "ok", "updated", "failed", "detail"]
    assert status["last_ok"] is not None


# ---------------------------------------------------------------- snapshots, plan, goals, prefs
def test_snapshot_upserts_one_row_per_day(session):
    import portfolio as pf
    from db.models import PortfolioSnapshot
    day = date(2001, 1, 1)
    held = [{"present": 100.0, "invested": 80.0, "grp": "", "sip_amount": 0}]
    pf.record_snapshot(session, held, today=day)
    pf.record_snapshot(session, [{**held[0], "present": 150.0}], today=day)
    rows = session.query(PortfolioSnapshot).filter(PortfolioSnapshot.snap_date == "2001-01-01").all()
    assert len(rows) == 1 and rows[0].total == 150.0 and json.loads(rows[0].groups)["Others"]["present"] == 150.0
    session.delete(rows[0])
    session.commit()


@pytest.fixture
def restore_plan(session):
    """Puts back the plan keys and the column layout this test changes."""
    from db.models import PortfolioPlan
    from db.models.portfolio import AppPref
    keys = ("targets", "mix_targets", "mix_returns", "mix_years", "mix_reach_years")
    before = {p.key: p.value for p in session.query(PortfolioPlan).filter(PortfolioPlan.key.in_(keys))}
    pref = session.get(AppPref, "holding_columns")
    pref_before = pref.value if pref else None
    session.close()
    yield
    for p in session.query(PortfolioPlan).filter(PortfolioPlan.key.in_(keys)).all():
        if p.key in before:
            p.value = before[p.key]
        else:
            session.delete(p)
    pref = session.get(AppPref, "holding_columns")
    if pref_before is None and pref:
        session.delete(pref)
    elif pref:
        pref.value = pref_before
    session.commit()


def test_plan_goals_and_holding_columns(client, restore_plan):
    plan = client.get(f"{API}/portfolio/plan").json()
    assert plan["groups"][-1] == "Others" and len(plan["goals"]) >= 1
    seeded = len(plan["goals"])
    assert len(client.get(f"{API}/portfolio/plan").json()["goals"]) == seeded, "starter goals are seeded once"

    targets = {"Equity": 50, "Mutual Funds": 50}
    assert client.put(f"{API}/portfolio/plan", json={"targets": {"Equity": 10}}).status_code == 400
    assert client.put(f"{API}/portfolio/plan", json={"targets": targets}).json() == {"ok": True}
    assert client.get(f"{API}/portfolio/plan").json()["targets"] == targets

    g = client.post(f"{API}/portfolio/goals", json={"name": " ZZ Goal ", "target_amount": 1000, "target_year": 2040}).json()
    client.put(f"{API}/portfolio/goals/{g['id']}", json={"name": "ZZ Goal 2", "target_amount": 2000, "target_year": 2041})
    goal = next(x for x in client.get(f"{API}/portfolio/plan").json()["goals"] if x["id"] == g["id"])
    assert (goal["name"], goal["target_amount"], goal["target_year"]) == ("ZZ Goal 2", 2000, 2041)
    client.delete(f"{API}/portfolio/goals/{g['id']}")
    assert all(x["id"] != g["id"] for x in client.get(f"{API}/portfolio/plan").json()["goals"])

    cols = {"order": ["name", "present"], "hidden": ["sector"]}
    assert client.put(f"{API}/holding-columns", json=cols).json() == {"ok": True}
    assert client.put(f"{API}/holding-columns", json=cols).json() == {"ok": True}, "saving twice updates the one row"
    assert client.get(f"{API}/holding-columns").json() == cols

    mix = {"targets": {"Equity": 60, "Gold": 10, "Debt": 30}, "returns": {"Equity": 12, "Gold": 8, "Debt": 7}, "years": 10, "reach_years": 3}
    assert client.put(f"{API}/portfolio/mix-plan", json=mix).json() == {"ok": True}
    assert client.get(f"{API}/portfolio/mix").json()["reach_years"] == 3


def test_monthly_spend_averages_last_three_complete_months(session):
    import portfolio as pf
    from db.models import Category, Expense
    cat = session.query(Category).first()
    rows = [Expense(category_id=cat.id, date=d, amount=a, cashback=c, note="zz-spend")
            for d, a, c in (("1990-01-05", 100, 0), ("1990-02-05", 300, 100), ("1990-03-05", 500, 0),
                            ("1990-04-05", 900, 0), ("1990-05-05", 50, 0))]
    session.add_all(rows)
    session.commit()
    try:
        # "today" in May 1990: the complete months before it are Feb, Mar, Apr (Jan is the fourth)
        assert pf.monthly_spend(session, date(1990, 5, 20)) == pytest.approx((200 + 500 + 900) / 3)
    finally:
        for r in rows:
            session.delete(r)
        session.commit()
