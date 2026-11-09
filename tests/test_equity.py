"""The stock ledger: Console file import, replay with corporate actions, dividends by quarter / year, XIRR, the
reconciliation audit and the Yahoo refresh (stubbed). Every test uses its own user, so the data never overlaps."""
import io

import openpyxl
import pytest

API = "/spendlens/api"
HEADER = ["Symbol", "ISIN", "Trade Date", "Exchange", "Segment", "Series", "Trade Type", "Auction", "Quantity", "Price",
          "Trade ID", "Order ID", "Order Execution Time"]


def tradebook(trades, client_id="TEST01", period=("2022-04-01", "2024-03-31")):
    """An .xlsx laid out like Console's: a blank first column, client id and period above the table."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Equity"
    for _ in range(6):
        ws.append([])
    ws.append([None, "Client ID", client_id])
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append([None, f"Tradebook for Equity from {period[0]} to {period[1]}"])
    ws.append([])
    ws.append([None, ""])
    ws.append([])
    ws.append([None] + HEADER)
    for i, (sym, d, side, qty, price) in enumerate(trades):
        ws.append([None, sym, f"INE{sym[:3]}01", d, "NSE", "EQ", "EQ", side, False, float(qty), float(price), f"T{i}", f"O{i}", f"{d}T10:00:00"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def holdings(rows, as_of="2024-03-31", client_id="TEST01"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Equity"
    ws.append([None, "Client ID", client_id])
    ws.append([None, f"Equity Holdings Statement as on {as_of}"])
    ws.append([])
    ws.append([None, "Symbol", "ISIN", "Sector", "Quantity Available", "Quantity Discrepant", "Quantity Long Term",
               "Quantity Pledged (Margin)", "Quantity Pledged (Loan)", "Average Price", "Previous Closing Price"])
    for sym, qty in rows:
        ws.append([None, sym, "", "", qty, 0, qty, 0, 0, 50, 60])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def dividends(rows):
    lines = ["Symbol,Ex-date,Qty,Dividend per share,Total dividend"] + [f"{s},{d},{q},{p},{q * p}" for s, d, q, p in rows]
    return ("\n".join(lines) + "\n").encode()


class _Result:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


def upload(c, account, files):
    """Import files for the user signed in on client `c`, the way import_broker.py does (scoped session)."""
    import equity as eq
    import equity_import as imp
    from db.engine import SessionLocal

    uid = c.get(f"{API}/auth/me").json()["id"]
    with SessionLocal() as s:
        s.info["user_id"] = uid
        canon = eq.make_canonical(eq.all_events(s))
        try:
            return _Result(200, {"results": imp.import_files(s, account, files, lambda raw, known: eq.dividend_symbol(raw, known, canon))})
        except imp.ImportError_ as e:
            s.rollback()
            return _Result(400, {"detail": str(e)})


TRADES = [("ABC", "2023-01-10", "buy", 10, 100), ("ABC", "2024-01-10", "sell", 5, 80), ("XYZ", "2023-05-01", "sell", 4, 10)]
DIVS = [("ABC6", "2023-07-01", 20, 2)]   # Console's suffixed symbol; 20 shares = 10 bought x the 2:1 split


@pytest.fixture
def user(make_user):
    c, _ = make_user(modules=["ledger"])
    return c


def _issues(c, kind=None):
    issues = c.get(f"{API}/equity/audit").json()["issues"]
    return [i for i in issues if kind is None or i["kind"] == kind]


def test_import_is_idempotent_and_reconciles_once_the_split_is_known(user):
    c = user
    files = [("tradebook-TEST01-EQ.xlsx", tradebook(TRADES)), ("dividends_2023-04-01_to_2024-03-31.csv", dividends(DIVS)),
             ("holdings-TEST01.xlsx", holdings([("ABC", 15)]))]
    r = upload(c, "sk", files)
    assert r.status_code == 200, r.text
    kinds = {x["kind"]: x["summary"] for x in r.json()["results"]}
    assert kinds["tradebook"].startswith("3 trades added")
    again = upload(c, "SK", files).json()["results"]
    assert next(x for x in again if x["kind"] == "tradebook")["summary"].startswith("0 trades added, 3 already present")

    # without the split the statement's 20 shares can't be explained
    mism = _issues(c, "qty_mismatch")
    assert len(mism) == 1 and mism[0]["symbol"] == "ABC" and mism[0]["replay"] == 10 and "2.00" in mism[0]["hint"]
    assert any(i["kind"] == "oversold" and i["symbol"] == "XYZ" for i in _issues(c))

    assert c.post(f"{API}/equity/events", json={"symbol": "ABC", "ex_date": "2023-06-01", "kind": "SPLIT",
                                               "ratio_new": 2, "ratio_old": 1}).status_code == 201
    assert _issues(c, "qty_mismatch") == []
    assert _issues(c, "holding_mismatch") == [], "15 shares after split and sale match the holdings statement"
    checks = c.get(f"{API}/equity/audit").json()["holdings_checks"]
    assert checks == [{"account": "SK", "as_of": "2024-03-31", "total": 1, "matched": 1}]

    s = c.get(f"{API}/equity/summary").json()
    abc = next(x for x in s["stocks"] if x["symbol"] == "ABC")
    assert abc["qty"] == 15 and abc["invested"] == pytest.approx(750) and abc["avg_cost"] == 50
    assert abc["realized"] == pytest.approx(5 * 80 - 5 * 50), "FIFO lots, cost halved by the split"
    assert abc["dividends"] == 40 and abc["xirr"] is None and "price" in abc["xirr_note"]
    assert abc["sold_qty"] == 5 and abc["sale_value"] == 400 and abc["exit_price"] is None, "still held: no exit yet"
    xyz = next(x for x in s["stocks"] if x["symbol"] == "XYZ")
    assert xyz["status"] == "exited" and (xyz["exit_qty"], xyz["exit_price"], xyz["exit_value"]) == (4, 10, 40)
    d = s["dividends"]
    assert d["quarters"] == ["FY2023-24 Q2"] and d["rows"][0]["by_year"] == {"FY2023-24": 40}
    assert s["accounts"] == ["SK"] and s["coverage"]["SK"]["statement_to"] == "2024-03-31"
    log = c.get(f"{API}/equity/audit").json()["log"]
    assert {x["kind"] for x in log} >= {"tradebook", "dividends", "holdings", "event"}


def test_a_file_cannot_be_imported_under_another_account(user):
    assert upload(user, "SK", [("t.xlsx", tradebook(TRADES))]).status_code == 200
    r = upload(user, "SS", [("t.xlsx", tradebook(TRADES))])
    assert r.status_code == 400 and "already imported as account SK" in r.json()["detail"]
    assert upload(user, "SS", [("notes.txt", b"hello")]).status_code == 400
    assert upload(user, "", [("t.xlsx", tradebook(TRADES))]).status_code == 400


def test_demerger_moves_cost_and_ipo_without_price_is_flagged(user):
    c = user
    upload(c, "SK", [("t.xlsx", tradebook([("PAR", "2023-01-02", "buy", 8, 100)]))])
    assert c.post(f"{API}/equity/events", json={"symbol": "PAR", "ex_date": "2023-03-01", "kind": "DEMERGER",
                                               "ratio_new": 1, "ratio_old": 4, "target_symbol": "KID", "cost_pct": 25}).status_code == 201
    assert c.post(f"{API}/equity/events", json={"account": "SK", "symbol": "NEW", "ex_date": "2023-04-01", "kind": "IPO",
                                               "qty": 10}).status_code == 201
    s = {x["symbol"]: x for x in c.get(f"{API}/equity/summary").json()["stocks"]}
    assert s["KID"]["qty"] == 2 and s["KID"]["invested"] == pytest.approx(200)
    assert s["PAR"]["qty"] == 8 and s["PAR"]["invested"] == pytest.approx(600)
    assert s["NEW"]["xirr_note"].startswith("Some shares have no cost")
    assert any(i["kind"] == "cost_unknown" and i["symbol"] == "NEW" for i in _issues(c))
    # validation
    bad = c.post(f"{API}/equity/events", json={"symbol": "PAR", "ex_date": "2023-03-01", "kind": "SPLIT"})
    assert bad.status_code == 400
    assert c.post(f"{API}/equity/events", json={"symbol": "PAR", "ex_date": "nope", "kind": "IPO", "qty": 1}).status_code == 400


def test_refresh_fills_dividends_after_the_statement_and_undoes_yahoo_adjustment(user, monkeypatch):
    import dividend_agent

    c = user
    upload(c, "SK", [("t.xlsx", tradebook(TRADES)), ("dividends_2023-04-01_to_2024-03-31.csv", dividends(DIVS))])
    c.post(f"{API}/equity/events", json={"symbol": "ABC", "ex_date": "2023-06-01", "kind": "SPLIT", "ratio_new": 2, "ratio_old": 1})

    def fake(ysym):
        if ysym != "ABC.NS":
            raise RuntimeError("HTTP Error 404")
        # a 5:1 split in 2025 that no event has yet: Yahoo shows the 2024 dividend of 3.0 as 0.6
        return {"price": 20.0, "price_date": "2025-06-01", "name": "ABC Ltd",
                "splits": [("2023-06-01", 2.0, 1.0), ("2025-02-01", 5.0, 1.0)],
                "dividends": [("2023-07-01", 0.4), ("2024-08-01", 0.6)]}
    monkeypatch.setattr(dividend_agent, "fetch", fake)
    r = c.post(f"{API}/equity/refresh")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["splits_added"] == [["ABC", "2025-02-01", "5:1"]], "the matching 2023 split is not added twice"
    assert out["dividends_added"] == 1 and out["failed"] == 1 and out["warnings"] == 0, out

    s = c.get(f"{API}/equity/summary").json()
    abc = next(x for x in s["stocks"] if x["symbol"] == "ABC")
    assert abc["qty"] == 75 and abc["price"] == 20 and abc["value"] == 1500
    assert abc["dividends"] == pytest.approx(40 + 15 * 3.0), "15 shares held before the 2024 ex-date, at the real ₹3"
    assert abc["xirr"] is not None and abc["xirr_ex_div"] is not None and abc["xirr"] > abc["xirr_ex_div"]
    row = next(r for r in s["dividends"]["rows"] if r["symbol"] == "ABC")
    assert row["by_quarter"] == {"FY2023-24 Q2": 40, "FY2024-25 Q2": 45} and row["sources"] == ["yahoo", "zerodha"]

    xyz = next(x for x in s["stocks"] if x["symbol"] == "XYZ")
    assert xyz["status"] == "exited" and xyz["price"] is None and xyz["change_since_exit_pct"] is None, "XYZ's fetch failed"

    again = c.post(f"{API}/equity/refresh").json()
    assert again["dividends_added"] == 0 and again["dividends_updated"] == 0 and again["splits_added"] == []

    # a later statement replaces the fetched row with what was actually paid
    res = upload(c, "SK", [("dividends_2024-04-01_to_2025-03-31.csv", dividends([("ABC", "2024-08-01", 15, 3.1)]))]).json()
    assert "1 fetched rows replaced" in res["results"][0]["summary"]
    row = next(r for r in c.get(f"{API}/equity/summary").json()["dividends"]["rows"] if r["symbol"] == "ABC")
    assert row["by_year"]["FY2024-25"] == pytest.approx(46.5) and row["sources"] == ["zerodha"]


def test_exited_stock_compares_todays_price_with_a_split_adjusted_exit(user, monkeypatch):
    import dividend_agent

    upload(user, "SK", [("t.xlsx", tradebook([("OLD", "2023-01-02", "buy", 4, 8), ("OLD", "2023-05-01", "sell", 4, 10)]))])
    # 5:1 split long after the exit, then the price: 3 now = 15 before the split, so +50% on the exit at 10
    monkeypatch.setattr(dividend_agent, "fetch", lambda y: {"price": 3.0, "price_date": "2026-11-06", "name": "Old Co",
                                                            "splits": [("2020-01-01", 2.0, 1.0), ("2024-01-01", 5.0, 1.0)], "dividends": []})
    out = user.post(f"{API}/equity/refresh").json()
    assert out["splits_added"] == [["OLD", "2024-01-01", "5:1"]], "the split after the exit is kept, the one before buying is not"
    old = next(x for x in user.get(f"{API}/equity/summary").json()["stocks"] if x["symbol"] == "OLD")
    assert old["status"] == "exited" and old["exit_qty"] == 4 and old["exit_price"] == 10 and old["price"] == 3
    assert old["split_factor_since_exit"] == 5 and old["exit_price_adj"] == 2 and old["change_since_exit_pct"] == 50
    assert old["exit_value_now"] == pytest.approx(4 * 5 * 3) and old["qty"] == 0 and old["realized"] == 8


def test_stock_detail_lists_history(user):
    upload(user, "SK", [("t.xlsx", tradebook(TRADES)), ("dividends_2023-04-01_to_2024-03-31.csv", dividends(DIVS))])
    d = user.get(f"{API}/equity/stock/abc").json()
    assert [t["kind"] for t in d["timeline"]] == ["BUY", "SELL"] and d["dividends"][0]["amount"] == 40


def test_exit_is_the_closing_run_of_sales(user):
    """Bought, sold out, bought again, then sold out in two lots: the exit is the last two sales only."""
    trades = [("RE", "2023-01-02", "buy", 10, 100), ("RE", "2023-02-01", "sell", 10, 120),
              ("RE", "2023-03-01", "buy", 6, 90), ("RE", "2023-04-03", "sell", 2, 150), ("RE", "2023-05-02", "sell", 4, 135)]
    upload(user, "SK", [("t.xlsx", tradebook(trades))])
    user.post(f"{API}/equity/events", json={"account": "SK", "symbol": "RE", "ex_date": "2023-04-20", "kind": "BUYBACK",
                                           "qty": 0.0001, "price": 1})   # a priced buyback in the closing run counts too
    re_ = next(x for x in user.get(f"{API}/equity/summary").json()["stocks"] if x["symbol"] == "RE")
    assert re_["status"] == "exited" and re_["exit_date"] == "2023-05-02"
    assert re_["exit_qty"] == pytest.approx(6.0001) and re_["exit_price"] == pytest.approx((2 * 150 + 4 * 135 + 0.0001) / 6.0001, abs=0.01)
    assert re_["sold_qty"] == pytest.approx(16.0001) and re_["sale_value"] == pytest.approx(1200 + 300 + 540, abs=0.01)


def test_stock_ledger_is_private(make_user):
    a, _ = make_user(modules=["ledger"])
    b, _ = make_user(modules=["ledger"])
    upload(a, "SK", [("t.xlsx", tradebook(TRADES)), ("dividends_2023-04-01_to_2024-03-31.csv", dividends(DIVS))])
    eid = a.post(f"{API}/equity/events", json={"symbol": "ABC", "ex_date": "2023-06-01", "kind": "SPLIT",
                                              "ratio_new": 2, "ratio_old": 1}).json()["id"]
    sb = b.get(f"{API}/equity/summary").json()
    assert sb["stocks"] == [] and sb["accounts"] == [] and sb["dividends"]["rows"] == []
    assert b.get(f"{API}/equity/audit").json()["log"] == []
    assert not [e for e in b.get(f"{API}/equity/events").json()["events"] if e["source"] != "builtin"]
    assert b.delete(f"{API}/equity/events/{eid}").status_code == 404
    assert b.put(f"{API}/equity/events/{eid}", json={"symbol": "ABC", "ex_date": "2023-06-01", "kind": "SPLIT",
                                                    "ratio_new": 9, "ratio_old": 1}).status_code == 404
    assert any(e["id"] == eid for e in a.get(f"{API}/equity/events").json()["events"])
    aid = a.get(f"{API}/equity/audit").json()["log"][0]["id"]
    assert b.get(f"{API}/equity/audit/{aid}").status_code == 404
    # B may import the same client's file under its own account name: the client-id check is per user
    assert upload(b, "SS", [("t.xlsx", tradebook(TRADES))]).status_code == 200


def test_another_users_imports_and_refresh_leave_my_rows_alone(make_user, monkeypatch):
    """The two bulk deletes (holdings statement, dividend period) and the refresh must only touch the caller's rows,
    even when both users use the same account label."""
    import dividend_agent

    a, _ = make_user(modules=["ledger"])
    b, _ = make_user(modules=["ledger"])
    upload(a, "SK", [("t.xlsx", tradebook(TRADES)), ("dividends_2023-04-01_to_2024-03-31.csv", dividends(DIVS)),
                     ("h.xlsx", holdings([("ABC", 15)]))])
    a.put(f"{API}/equity/securities/ABC", json={"yahoo_symbol": "ABC.BO"})
    before = a.get(f"{API}/equity/summary").json()
    checks = a.get(f"{API}/equity/audit").json()["holdings_checks"]

    assert b.post(f"{API}/equity/refresh").status_code == 400, "B has no trades of its own"
    upload(b, "SK", [("t2.xlsx", tradebook([("ABC", "2023-02-01", "buy", 1, 1)], client_id="OTHER")),
                     ("dividends_2023-04-01_to_2024-03-31.csv", dividends([("ABC", "2023-07-01", 1, 9)])),
                     ("h.xlsx", holdings([("ABC", 1)], client_id="OTHER"))])
    b.put(f"{API}/equity/securities/ABC", json={"yahoo_symbol": "HIJACK.NS"})
    calls = []
    monkeypatch.setattr(dividend_agent, "fetch", lambda y: calls.append(y) or {"price": 5.0, "price_date": "2025-01-01", "name": "",
                                                                                "splits": [], "dividends": []})
    assert b.post(f"{API}/equity/refresh").status_code == 200
    assert calls == ["HIJACK.NS"], "B's refresh uses B's own override and fetches only B's symbols"

    after = a.get(f"{API}/equity/summary").json()
    assert after["dividends"] == before["dividends"] and after["stocks"] == before["stocks"]
    assert a.get(f"{API}/equity/audit").json()["holdings_checks"] == checks
    calls.clear()
    assert a.post(f"{API}/equity/refresh").status_code == 200
    assert sorted(calls) == ["ABC.BO", "XYZ.NS"], "A's own override, not B's, and only A's symbols"


def test_needs_the_ledger_module(make_user):
    c, _ = make_user(modules=["holdings"])
    assert c.get(f"{API}/equity/summary").status_code == 403
    assert c.post(f"{API}/equity/refresh").status_code == 403


def test_symbol_and_quarter_helpers():
    import equity as eq
    assert eq.fq_of("2025-04-01") == "FY2025-26 Q1" and eq.fq_of("2026-03-31") == "FY2025-26 Q4" and eq.fq_of("2025-12-31") == "FY2025-26 Q3"
    assert eq.dividend_symbol("BAJFINANCE6", {"BAJFINANCE"}) == "BAJFINANCE"
    assert eq.dividend_symbol("INFY#", {"INFY"}) == "INFY"
    assert eq.dividend_symbol("MCDOWELL-N", {"MCDOWELL-N"}, eq.make_canonical([])) == "UNITDSPR"
    assert eq.factor({"kind": "BONUS", "ratio_new": 1, "ratio_old": 1}) == 2
    assert eq.factor({"kind": "SPLIT", "ratio_new": 5, "ratio_old": 1}) == 5


def test_import_folder_reads_one_subfolder_per_account(make_user, tmp_path):
    import import_broker
    from db.engine import SessionLocal

    c, u = make_user(modules=["ledger"])
    (tmp_path / "sk").mkdir()
    (tmp_path / "sk" / "tradebook-TEST01-EQ.xlsx").write_bytes(tradebook(TRADES))
    (tmp_path / "sk" / "tradebook-TEST01-EQ (1).xlsx").write_bytes(tradebook(TRADES))   # Console's duplicate download
    (tmp_path / "sk" / "dividends_2023-04-01_to_2024-03-31.csv").write_bytes(dividends(DIVS))
    (tmp_path / "sk" / "notes.md").write_text("ignored")
    with SessionLocal() as s:
        s.info["user_id"] = u["id"]
        out = import_broker.import_folder(s, tmp_path, log=lambda *_: None)
    assert list(out) == ["SK"] and len(out["SK"]) == 3
    assert sorted(r["summary"].split(",")[0] for r in out["SK"] if r["kind"] == "tradebook") == ["0 trades added", "3 trades added"]
    assert c.get(f"{API}/equity/summary").json()["accounts"] == ["SK"]
    assert c.post(f"{API}/equity/import").status_code in (404, 405), "no upload endpoint"
