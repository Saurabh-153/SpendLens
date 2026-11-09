"""MF Analysis: the extracted-factsheet format (mf.validate), its import (merge of factsheet + portfolio files),
the analysis (matching to holdings, series, anomalies, overlap, coverage), the folder helpers, and privacy."""
import json
from pathlib import Path

import openpyxl
import pytest

API = "/spendlens/api"


def fund(scheme="ZZ Alpha Mid-Cap Opportunities Fund", **kw):
    f = {"scheme": scheme, "plan": "Direct", "amfi_code": kw.pop("amfi_code", ""), "category": kw.pop("category", "Mid Cap"),
         "benchmark": "NIFTY Midcap 150 TRI", "aum_cr": 50000, "ter_pct": 0.7, "std_dev": 14.0, "beta": 0.9, "sharpe": 1.1,
         "turnover_pct": 20, "cap_mix": {"large": 10, "mid": 70, "small": 18},
         "returns": {"1y": 12, "3y": 22, "5y": 25}, "benchmark_returns": {"1y": 10, "3y": 20, "5y": 24},
         "managers": [{"name": "A. Manager", "since": "2015-01-01"}]}
    f.update(kw)
    return f


def payload(month, funds, source="ZZAMC.pdf", kind="factsheet"):
    return {"month": month, "source": source, "source_sha256": "x", "kind": kind, "amc": "ZZ AMC", "funds": funds}


def holdings(*rows):
    return [{"name": n, "isin": i, "pct": p, "sector": "", "rating": r} for n, i, p, r in rows]


def scoped(uid):
    from db.engine import SessionLocal
    s = SessionLocal()
    s.info["user_id"] = uid
    return s


@pytest.fixture
def mfuser(make_user):
    c, u = make_user(modules=["holdings"])
    return c, u["id"]


def test_validate_rejects_misread_figures():
    import mf
    assert mf.validate(payload("2026-10", [fund()])) == ([], [])
    errors, _ = mf.validate(payload("2026-13", [fund(ter_pct=7.5, beta="0.9"), fund()]))
    joined = " | ".join(errors)
    assert "YYYY-MM" in joined and "ter_pct = 7.5" in joined and "beta must be a number" in joined and "listed twice" in joined
    over = fund(holdings=holdings(("A", "", 60, ""), ("B", "", 50, "")))
    assert any("add up to 110.0%" in e for e in mf.validate(payload("2026-10", [over]))[0])
    part = fund(holdings=holdings(("A", "", 30, "")))
    assert any("only 30.0%" in w for w in mf.validate(payload("2026-10", [part]))[1])


def test_scheme_key_and_rating_rank():
    import mf
    assert mf.scheme_key("HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth", "Direct") == "hdfc mid cap opportunities|direct"
    assert mf.scheme_key("HDFC Mid Cap Opportunities", "direct") == "hdfc mid cap opportunities|direct"
    assert mf.scheme_key("Parag Parikh Flexi Cap Fund (Folio: 12345678)") == mf.scheme_key("Parag Parikh Flexi Cap Fund (Folio: 87654321)") \
        == "parag parikh flexi cap", "folios are one fund"
    assert mf.rating_rank("CRISIL AAA") < mf.rating_rank("ICRA AA+") < mf.rating_rank("CARE AA") < mf.rating_rank("AA-")
    assert mf.rating_rank("SOVEREIGN") == 0 and mf.rating_rank("unrated") is None


def test_import_merges_months_and_files_and_flags_anomalies(mfuser):
    import mf
    c, uid = mfuser
    for name, code in (("ZZ Alpha Mid-Cap Opportunities Fund - Direct Plan", "990001"), ("ZZ Beta Flexi Cap Fund Direct Growth", "")):
        r = c.post(f"{API}/holdings", json={"name": name, "asset_type": "MF", "qty": 1, "buy_price": 100000, "cmp": 120000})
        assert r.status_code == 201, r.text
    beta_fund = dict(scheme="ZZ Beta Flexi Cap Fund", category="Flexi Cap")
    months = [("2026-07", 0.70, 50000, 4.0), ("2026-08", 0.70, 52000, 4.0), ("2026-09", 0.71, 53000, 4.5), ("2026-10", 0.85, 41000, 11.0)]
    with scoped(uid) as s:
        for m, ter, aum, cash in months:
            mgr = [{"name": "B. New", "since": "2026-10-01"}] if m == "2026-10" else [{"name": "A. Manager", "since": "2015-01-01"}]
            mf.import_payload(s, payload(m, [fund(amfi_code="990001", ter_pct=ter, aum_cr=aum, cash_pct=cash, managers=mgr),
                                             fund(**beta_fund)]))
        # the month's portfolio disclosure adds the holdings without touching the ratios
        port = payload("2026-10", [
            {"scheme": "ZZ Alpha Mid-Cap Opportunities Fund", "plan": "Direct",
             "holdings": holdings(("Shared Co", "INE101A01011", 6, ""), ("Only Alpha", "INE102A01011", 4, ""), ("TREPS", "", 11, ""))},
            {"scheme": "ZZ Beta Flexi Cap Fund", "plan": "Direct",
             "holdings": holdings(("Shared Co", "INE101A01011", 5, ""), ("Only Beta", "INE103A01011", 7, ""))},
        ], source="ZZAMC-portfolio.xlsx", kind="portfolio")
        mf.import_payload(s, port)
        s.commit()

    a = c.get(f"{API}/mf/analysis").json()
    assert a["has_data"] and a["latest_month"] == "2026-10" and a["unmatched_holdings"] == []
    alpha = next(f for f in a["funds"] if f["name"].startswith("ZZ Alpha"))
    assert alpha["held"] and alpha["value"] == 120000 and alpha["months"] == [m for m, *_ in months]
    assert alpha["latest"]["ter"] == 0.85 and alpha["latest"]["vsBench3y"] == 2 and alpha["latest"]["cash"] == 11
    assert [p["value"] for p in alpha["series"]["ter"]] == [0.70, 0.70, 0.71, 0.85] and alpha["holdings_count"] == 3
    assert alpha["manager"] == "B. New" and alpha["manager_years"] == 0.1
    rules = {(x["fund"], x["rule"]) for x in a["anomalies"]}
    for rule in ("Fund manager changed", "Expense ratio up", "AUM fell sharply", "Cash pile-up"):
        assert ("ZZ Alpha Mid-Cap Opportunities Fund", rule) in rules, rule
    assert not any(f.startswith("ZZ Beta") for f, _ in rules)
    assert len(a["overlap"]) == 1, "one pair of held equity funds"
    pair = a["overlap"][0]
    assert {pair["a"], pair["b"]} == {alpha["name"], "ZZ Beta Flexi Cap Fund"}
    assert pair["pct"] == 5.0 and pair["shared"] == ["Shared Co"], "min(6, 5) of the shared stock; TREPS is cash, not a holding"
    assert a["coverage"] == [{"amc": "ZZ AMC", "months": [{"month": m, "loaded": True} for m, *_ in months]}]
    assert {x["file"] for x in a["sources"]} >= {"ZZAMC.pdf", "ZZAMC-portfolio.xlsx"}


def test_mandate_drift_and_credit_downgrade(mfuser):
    import mf
    c, uid = mfuser
    with scoped(uid) as s:
        mf.import_payload(s, payload("2026-09", [fund("ZZ Large Fund", category="Large Cap", cap_mix={"large": 85, "mid": 10, "small": 5}),
                                                 fund("ZZ Bond Fund", category="Debt", holdings=holdings(("7% Some Co NCD", "INE111A07011", 90, "CRISIL AAA")))]))
        mf.import_payload(s, payload("2026-10", [fund("ZZ Large Fund", category="Large Cap", cap_mix={"large": 72, "mid": 18, "small": 10}),
                                                 fund("ZZ Bond Fund", category="Debt", holdings=holdings(("7% Some Co NCD", "INE111A07011", 90, "CRISIL AA")))]))
        s.commit()
    rules = {(x["fund"], x["rule"]) for x in c.get(f"{API}/mf/analysis").json()["anomalies"]}
    assert ("ZZ Large Fund", "Outside its mandate") in rules and ("ZZ Bond Fund", "Credit downgrade") in rules


def test_bad_file_stops_the_whole_import(mfuser, tmp_path):
    import import_mf
    _, uid = mfuser
    (tmp_path / "_extracted" / "2026-10").mkdir(parents=True)
    (tmp_path / "_extracted" / "2026-10" / "Good.json").write_text(json.dumps(payload("2026-10", [fund()], source="Good.pdf")))
    (tmp_path / "_extracted" / "2026-10" / "Bad.json").write_text(json.dumps(payload("2026-09", [fund()], source="Bad.pdf")))
    with scoped(uid) as s, pytest.raises(SystemExit) as e:
        import_mf.load_folder(s, tmp_path, log=lambda *_: None)
    assert "month 2026-09 but the folder is 2026-10" in str(e.value)
    with scoped(uid) as s:
        from db.models import MfFundMonth
        assert s.query(MfFundMonth).count() == 0, "nothing saved"
        (tmp_path / "_extracted" / "2026-10" / "Bad.json").unlink()
        assert len(import_mf.load_folder(s, tmp_path, log=lambda *_: None)) == 1


def test_extract_helpers_inventory_find_and_text(tmp_path):
    import mf_extract
    month = tmp_path / "2026-10"
    month.mkdir()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ZZ Alpha"
    ws.append(["Name of the Instrument", "ISIN", "% to NAV"])
    ws.append(["Shared Co", "INE101A01011", 6.1])
    wb.save(month / "ZZAMC-portfolio.xlsx")
    (month / "fake.xls").write_bytes(b"not an excel file")
    inv = mf_extract.inventory(tmp_path)
    files = {f["file"]: f for f in inv["months"][0]["files"]}
    key = str(Path("2026-10") / "ZZAMC-portfolio.xlsx")
    assert files[key]["status"] == "new" and files[str(Path("2026-10") / "fake.xls")]["status"].startswith("unsupported")
    assert inv["todo"] == 1
    out = mf_extract.extracted_path(tmp_path, "2026-10", "ZZAMC-portfolio.xlsx")
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"source_sha256": files[key]["sha256"]}))
    assert {f["file"]: f["status"] for f in mf_extract.inventory(tmp_path)["months"][0]["files"]}[key] == "done"
    assert mf_extract.find(month / "ZZAMC-portfolio.xlsx", "shared co")[0]["where"] == "sheet ZZ Alpha"
    assert "INE101A01011\t6.1" in mf_extract.text(month / "ZZAMC-portfolio.xlsx")


def test_mf_analysis_is_private_and_gated(mfuser, make_user):
    import mf
    c, uid = mfuser
    with scoped(uid) as s:
        mf.import_payload(s, payload("2026-10", [fund("ZZ Private Fund")]))
        s.commit()
    assert c.get(f"{API}/mf/analysis").json()["has_data"]
    other, _ = make_user(modules=["holdings"])
    b = other.get(f"{API}/mf/analysis").json()
    assert not b["has_data"] and b["funds"] == [] and b["sources"] == []
    no_module, _ = make_user(modules=["expense"])
    assert no_module.get(f"{API}/mf/analysis").status_code == 403


def test_buying_trend_by_year_and_folios_shown_once(mfuser):
    """Shares decide buying vs price moves; a year runs from the previous year's last factsheet; two folios of one
    fund are one fund; the across-funds view counts funds buying the same stock."""
    import mf
    c, uid = mfuser
    for folio in ("Folio 1", "Folio 2"):
        assert c.post(f"{API}/holdings", json={"name": "ZZ Gamma Flexi Cap Fund Direct Growth", "asset_type": "MF", "qty": 1,
                                              "buy_price": 1, "cmp": 50000, "notes": folio}).status_code == 201
    assert c.post(f"{API}/holdings", json={"name": "ZZ Delta Focused Fund", "asset_type": "MF", "qty": 1, "buy_price": 1, "cmp": 1000}).status_code == 201

    def snap(rows):
        return [{"name": n, "isin": i, "pct": p, "qty": q} for n, i, p, q in rows]
    g = {"scheme": "ZZ Gamma Flexi Cap Fund", "plan": "Direct", "category": "Flexi Cap"}
    d = {"scheme": "ZZ Delta Focused Fund", "plan": "", "category": "Focused"}
    with scoped(uid) as s:
        for month, gh, dh in (
            ("2025-12", [("Steady Co", "INE201A01011", 5.0, 200), ("Added Co", "INE202A01011", 3.0, 100), ("Gone Co", "INE203A01011", 2.0, 50)],
                        [("Added Co", "INE202A01011", 4.0, None)]),
            ("2026-06", [("Steady Co", "INE201A01011", 6.0, 200), ("Added Co", "INE202A01011", 4.0, 130), ("Gone Co", "INE203A01011", 1.0, 20)],
                        [("Added Co", "INE202A01011", 4.1, None)]),
            ("2026-10", [("Steady Co", "INE201A01011", 7.5, 200), ("Added Co", "INE202A01011", 5.0, 150), ("New Co", "INE204A01011", 2.0, 80),
                         ("TREPS", "", 3.0, None)],
                        [("Added Co", "INE202A01011", 5.5, None)]),
        ):
            mf.import_payload(s, payload(month, [{**g, "holdings": snap(gh)}, {**d, "holdings": snap(dh)}], kind="portfolio"))
        s.commit()
    a = c.get(f"{API}/mf/analysis").json()
    gammas = [f for f in a["funds"] if f["name"] == "ZZ Gamma Flexi Cap Fund"]
    assert len(gammas) == 1 and gammas[0]["value"] == 100000, "two folios, one fund, values added"
    assert [u["name"] for u in a["unmatched_holdings"]] == []

    t = gammas[0]["trends"]
    assert t["months_with_holdings"] == ["2025-12", "2026-06", "2026-10"]
    y = next(x for x in t["years"] if x["year"] == "2026")
    assert (y["from"], y["to"], y["basis"]) == ("2025-12", "2026-10", "shares")
    st = {r["stock"]: r for r in y["rows"]}
    assert st["Added Co"]["status"] == "added" and st["Added Co"]["qty_change_pct"] == 50.0
    assert st["Steady Co"]["status"] == "held", "weight rose 5% -> 7.5% on price alone; the share count did not change"
    assert st["Gone Co"]["status"] == "exited" and st["New Co"]["status"] == "new" and "TREPS" not in st
    assert y["counts"] == {"new": 1, "added": 1, "trimmed": 0, "exited": 1, "held": 1}
    assert [r["status"] for r in y["rows"]][:2] == ["new", "added"], "new and added positions first"
    assert t["latest"]["from"] == "2026-06" and {r["stock"]: r["status"] for r in t["latest"]["rows"]}["Gone Co"] == "exited"

    dy = next(f for f in a["funds"] if f["name"] == "ZZ Delta Focused Fund")["trends"]["years"][0]
    assert dy["basis"] == "weight" and dy["rows"][0]["status"] == "added" and dy["rows"][0]["weight_change"] == 1.5

    moves = a["market_moves"]
    added = next(m for m in moves["by_year"]["2026"] if m["stock"] == "Added Co")
    assert moves["funds"] == 2 and sorted(added["buying"]) == ["ZZ Delta Focused Fund", "ZZ Gamma Flexi Cap Fund"] and added["net"] == 2
    assert moves["by_year"]["2026"][0]["stock"] == "Added Co", "the stock most of your funds are buying comes first"


def test_month_from_file_names_and_a_flat_folder(tmp_path):
    import mf_extract
    for name, month in (("ppfas-mf-factsheet-for-April-2024.pdf", "2024-04"), ("PPFAS_Monthly_Portfolio_Report_February_29_2024.xlsx", "2024-02"),
                        ("HDFC_factsheet_2026-10.pdf", "2026-10"), ("portfolio_10-2026.xlsx", "2026-10"), ("Sept 2025 factsheet.pdf", "2025-09"),
                        ("April_25.pdf", "2025-04"), ("AxisFundFactsheetFebruary2026.pdf", "2026-02"),
                        ("notes.pdf", None)):
        assert mf_extract.month_of(tmp_path / name) == month, name
    (tmp_path / "2026-05").mkdir()
    assert mf_extract.month_of(tmp_path / "2026-05" / "anything.pdf", tmp_path) == "2026-05", "a YYYY-MM folder wins"

    wb = openpyxl.Workbook()
    wb.active.append(["Name of the Instrument", "ISIN", "Quantity", "% to Net Assets"])
    wb.save(tmp_path / "PPFAS_Monthly_Portfolio_Report_May_31_2026.xls")   # an .xlsx with an .xls name, as AMCs publish
    (tmp_path / "ppfas-mf-factsheet-for-May-2026.pdf").write_bytes(b"%PDF-1.4 not really")
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / "_extracted" / "2026-05").mkdir(parents=True)
    (tmp_path / "_extracted" / "2026-05" / "old.json").write_text("{}")
    inv = mf_extract.inventory(tmp_path)
    assert [m["month"] for m in inv["months"]] == ["2026-05"] and inv["todo"] == 2
    kinds = {f["file"]: (f["kind_guess"], f["status"]) for f in inv["months"][0]["files"]}
    assert kinds == {"PPFAS_Monthly_Portfolio_Report_May_31_2026.xls": ("portfolio", "new"), "ppfas-mf-factsheet-for-May-2026.pdf": ("factsheet", "new")}
    assert inv["skipped"] == ["readme.txt (not a PDF / Excel / CSV)"], "_extracted is not inventoried"
    assert "Quantity" in mf_extract.text(tmp_path / "PPFAS_Monthly_Portfolio_Report_May_31_2026.xls")


def test_disclosure_holdings_win_over_the_factsheet_list(mfuser):
    """Whatever the import order, a factsheet's holdings (no share counts) never replace a disclosure's; deal-code
    cash lines are cash; arbitrage funds stay out of overlap and the buying view."""
    import mf
    c, uid = mfuser
    disc = {"scheme": "ZZ Order Fund", "holdings": [{"name": "Stock A", "isin": "INE301A01011", "pct": 95, "qty": 1000},
                                                    {"name": "TRP_011026", "isin": "", "pct": 5, "qty": None}]}
    fact = {"scheme": "ZZ Order Fund", "ter_pct": 0.6, "holdings": [{"name": "Stock A", "isin": "INE301A01011", "pct": 94.9}]}
    with scoped(uid) as s:
        mf.import_payload(s, payload("2026-09", [disc], source="P.xlsx", kind="portfolio"))
        mf.import_payload(s, payload("2026-09", [fact], source="F.pdf", kind="factsheet"))
        mf.import_payload(s, payload("2026-09", [{"scheme": "ZZ Arb Fund", "category": "Arbitrage",
                                                  "holdings": [{"name": "Stock A", "isin": "INE301A01011", "pct": 60, "qty": 5}]}], source="A.xlsx", kind="portfolio"))
        s.commit()
        from db.models import MfFundMonth, MfHolding
        row = s.query(MfFundMonth).filter(MfFundMonth.scheme == "ZZ Order Fund").one()
        hs = s.query(MfHolding).filter(MfHolding.fund_month_id == row.id).all()
        assert row.ter_pct == 0.6 and sorted(h.qty or 0 for h in hs) == [0, 1000], "ratios merged, disclosure holdings kept"
        assert row.cash_pct == 5 and row.top10_pct == 95, "TRP_ deal code counted as cash"
        # a later disclosure still replaces the earlier one
        mf.import_payload(s, payload("2026-09", [{**disc, "holdings": [{"name": "Stock B", "isin": "INE302A01011", "pct": 100, "qty": 7}]}],
                                     source="P.xlsx", kind="portfolio"))
        s.commit()
        assert [h.name for h in s.query(MfHolding).filter(MfHolding.fund_month_id == row.id)] == ["Stock B"]
    a = c.get(f"{API}/mf/analysis").json()
    assert a["overlap"] == [] and a["market_moves"]["funds"] == 1, "the arbitrage fund's hedged stocks are left out"


def test_locate_reads_index_lines_and_builds_page_ranges():
    """The pieces of locate that don't need a PDF: index lines in both styles (Axis 'name ....... 16' and
    'name 123 - 128'), start pages turned into ranges, and generic bookmarks rejected."""
    import mf_extract
    m = mf_extract.TOC_LINE.match("Axis Small Cap Fund ..................................................... 16")
    assert m and m.group("name").strip() == "Axis Small Cap Fund" and m.group("a") == "16"
    m = mf_extract.TOC_LINE.match("Axis Income Plus Arbitrage Passive FOF ………………………………… 116")
    assert m and m.group("a") == "116"
    m = mf_extract.TOC_RANGE.match("Expense Ratios 138 - 141")
    assert m and (m.group("name"), m.group("a"), m.group("b")) == ("Expense Ratios", "138", "141")
    assert not mf_extract.TOC_LINE.match("HDFC Bank Limited 7.75%"), "a holding line is not an index entry"
    starts = sorted({(8, "Axis Large Cap Fund", None), (16, "Axis Small Cap Fund", None), (17, "Axis ESG Fund", None),
                     (119, "Axis Gold Fund", None), (117, "Axis Multi-Asset Omni FoF", None), (138, "Expense Ratios", 141)})
    got = {t: (a, b) for t, a, b in mf_extract._ranges(starts, 171)}
    assert got["Axis Small Cap Fund"] == (16, 16) and got["Axis Large Cap Fund"] == (8, 15)
    assert got["Axis Multi-Asset Omni FoF"] == (117, 118), "entries listed out of order are sorted by page"
    assert got["Expense Ratios"] == (138, 141), "an explicit end wins"
    assert mf_extract.GENERIC_BOOKMARK.match("Slide 12") and not mf_extract.GENERIC_BOOKMARK.match("Axis Small Cap Fund")


def test_fund_manager_and_as_on_columns_and_amfi_merge(mfuser):
    """One row per fund per month even when the PDF and the Excel spell the scheme differently (same AMFI code);
    the manager names land in fund_manager and the printed date in as_on."""
    import mf
    from db.models import MfFundMonth, MfSource
    c, uid = mfuser
    with scoped(uid) as s:
        mf.import_payload(s, {"month": "2026-09", "as_on": "2026-09-30", "source": "F.pdf", "kind": "factsheet", "funds": [
            {"scheme": "ZZ Parag Flexi Cap Fund", "amfi_code": "990777", "ter_pct": 0.53,
             "managers": [{"name": "R. Thakkar", "since": "2013-05-24"}, {"name": "R. Onkar", "since": "2019-07-24"}]}]})
        mf.import_payload(s, {"month": "2026-09", "as_on": "2026-09-30", "source": "P.xlsx", "kind": "portfolio", "funds": [
            {"scheme": "ZZ Parag Flexi Cap Fund (An open-ended dynamic equity scheme)", "amfi_code": "990777",
             "holdings": [{"name": "HDFC Bank", "isin": "INE040A01034", "pct": 100, "qty": 10}]}]})
        mf.import_payload(s, {"month": "2026-09", "source": "F.pdf", "kind": "factsheet", "funds": [
            {"scheme": "ZZ Parag Flexi Cap Fund", "amfi_code": "990777", "ter_pct": 0.53}]})   # re-import: replaces, never duplicates
        s.commit()
        rows = s.query(MfFundMonth).filter(MfFundMonth.amfi_code == "990777").all()
        assert len(rows) == 1 and rows[0].fund_manager == "R. Thakkar, R. Onkar" and rows[0].as_on == "2026-09-30"
        assert s.query(MfSource).filter(MfSource.file_name == "F.pdf").count() == 1
    f = next(x for x in c.get(f"{API}/mf/analysis").json()["funds"] if x["amfi_code"] == "990777")
    assert f["manager"] == "R. Thakkar, R. Onkar" and f["as_on"] == "2026-09-30" and f["holdings_count"] == 1
    import mf as m2
    assert m2.validate({"month": "2026-09", "as_on": "2026-10-01", "source": "x", "funds": [{"scheme": "A"}]})[0] == ["as_on must be YYYY-MM-DD within the month"]


def test_split_with_new_isin_is_one_stock_and_cds_stay_out(mfuser):
    """Kotak-style 5:1 split: the ISIN changes (same issuer code) and shares ×5 at an unchanged weight -> one stock,
    held, noted as a split. A CD that matures and is replaced each month is not buying or selling."""
    import mf
    c, uid = mfuser
    c.post(f"{API}/holdings", json={"name": "ZZ Split Fund", "asset_type": "MF", "qty": 1, "buy_price": 1, "cmp": 10})

    def month(m, isin, qty, cd_isin, cd_name):
        return payload(m, [{"scheme": "ZZ Split Fund", "holdings": [
            {"name": "Kotak Mahindra Bank Limited", "isin": isin, "pct": 4.4, "qty": qty, "sector": "Banks"},
            {"name": "Real Buy Ltd", "isin": "INE555A01011", "pct": 2.0 if m == "2025-12" else 3.5, "qty": 100 if m == "2025-12" else 180},
            {"name": cd_name, "isin": cd_isin, "pct": 3.0, "qty": 500, "rating": "CRISIL A1+"}]}], kind="portfolio")
    with scoped(uid) as s:
        mf.import_payload(s, month("2025-12", "INE237A01028", 1000, "INE237A16AB1", "Kotak Mahindra Bank Limited (08/01/2026)"))
        mf.import_payload(s, month("2026-09", "INE237A01036", 5000, "INE237A16CD5", "Kotak Mahindra Bank Limited (08/12/2026)"))
        s.commit()
    f = next(x for x in c.get(f"{API}/mf/analysis").json()["funds"] if x["name"] == "ZZ Split Fund")
    rows = {r["stock"]: r for r in f["trends"]["years"][0]["rows"]}
    assert set(rows) == {"Kotak Mahindra Bank Limited", "Real Buy Ltd"}, "the CDs are not in the stock view"
    k = rows["Kotak Mahindra Bank Limited"]
    assert k["status"] == "held" and k["qty_change_pct"] == 0.0 and "split" in k["note"]
    assert rows["Real Buy Ltd"]["status"] == "added" and rows["Real Buy Ltd"]["qty_change_pct"] == 80.0


def test_axis_holdings_column_by_position():
    """The Axis portfolio column rebuilt from text positions: an industry wrapping above and below its row, a name
    printed around its % line, a capitalised derivative line kept, section headers and totals skipped."""
    import mf
    import mf_parsers
    W = 552.0
    P = [(638, 335, "Instrument Type/Issuer Name"), (638, 470, "Industry"), (638, 498, "% of NAV"),
         (630, 336.6, "EQUITY"), (630, 508, "90.32%"),
         (625, 336.6, "Krishna Institute Of Medical Sciences Limited"), (625, 450, "Healthcare Services"), (625, 510.8, "2.46%"),
         (619.4, 452.7, "Pharmaceuticals &"), (616.8, 336.6, "Torrent Pharmaceuticals Limited"), (616.8, 510.9, "2.32%"),
         (614.0, 460.9, "Biotechnology"),
         (600, 336.6, "NIFTY"), (600, 510, "2.74%"),
         (70.8, 336.6, "Other Domestic Equity (Less than 0.50% of the"), (68.1, 508.0, "13.81%"), (65.4, 336.6, "corpus)"),
         (60.0, 336.6, "Debt, Cash & other current assets"), (60.0, 510.8, "9.68%"),
         (54.6, 336.6, "Grand Total"), (54.6, 505.4, "100.00%"),
         (611.9, 271.5, "-"), (611.9, 275.4, "16.98%")]   # a left-column figure, ignored here
    lines, skipped = mf_parsers._axis_holdings(P, W)
    by = {x["name"]: x for x in lines}
    assert by["Torrent Pharmaceuticals Limited"]["sector"] == "Pharmaceuticals & Biotechnology"
    assert by["Krishna Institute Of Medical Sciences Limited"]["pct"] == 2.46
    assert "Other Domestic Equity (Less than 0.50% of the corpus)" in by and "NIFTY" in by
    assert skipped == ["EQUITY 90.32%", "Grand Total 100.0%"]

    class H:
        def __init__(self, name):
            self.name, self.isin, self.rating = name, "", ""
    assert not mf.is_stock(H("NIFTY")) and not mf.is_stock(H("Other Domestic Equity (Less than 0.50% of the corpus)"))
    assert mf.is_stock(H("Torrent Pharmaceuticals Limited"))


def test_parser_dates_accept_short_month_names():
    import mf_parsers
    assert mf_parsers._date("27", "Jun", "2014") == "2014-06-27"
    assert mf_parsers._date("22", "Sept", "2025") == "2025-09-22"
    assert mf_parsers._date("30", "September", "2026") == "2026-09-30"
    assert mf_parsers._date("31", "Feb", "2026") is None and mf_parsers._date("1", "Smarch", "2026") is None


def test_overlap_matches_names_when_a_factsheet_has_no_isin(mfuser):
    """A disclosure (ISINs) and a top-10-only factsheet (names only) still share stocks: matched by company name,
    and flagged partial because one side covers only part of its fund."""
    import mf
    from db.models import Holding
    c, uid = mfuser
    with scoped(uid) as s:
        for name, code in (("ZZ Ovl Flexi Fund Direct Growth", "990801"), ("ZZ Ovl Mid Fund (Folio: 9)", "990802")):
            s.add(Holding(name=name, asset_type="MF", scheme_code=code, qty=1, cmp=100))
        mf.import_payload(s, payload("2026-09", [fund("ZZ Ovl Flexi Fund", amfi_code="990801", category="Flexi Cap", holdings=holdings(
            ("The Federal Bank Limited", "INE171A01029", 40, ""), ("Coforge Limited", "INE591G01025", 30, ""), ("TREPS", "", 30, "")))],
            source="Ovl1.xlsx", kind="portfolio"))
        mf.import_payload(s, payload("2026-09", [fund("ZZ Ovl Mid Fund", amfi_code="990802", holdings=holdings(
            ("Federal Bank Ltd", "", 3.7, ""), ("Coforge Ltd", "", 2.2, ""), ("BSE Ltd", "", 2.0, "")))], source="Ovl2.pdf"))
        s.commit()
        assert mf.stock_name_key("The Federal Bank Ltd") == mf.stock_name_key("Federal Bank Limited") == "federal bank"
    got = c.get(f"{API}/mf/analysis").json()
    pair = next(p for p in got["overlap"] if {p["a"], p["b"]} == {"ZZ Ovl Flexi Fund", "ZZ Ovl Mid Fund"})
    assert pair["pct"] == 5.9 and pair["count"] == 2 and pair["partial"] is True


def morningstar_report(**kw):
    rep = {"fund": "ZZ Ms Small Cap Fund Direct Growth", "report_date": "2026-11-08", "portfolio_date": "2026-09-30",
           "isin": "INF000000001", "risk": {"alpha": 1.7, "beta": 0.76, "sharpe": 0.45, "std_dev": 17.4},
           "trailing": {"3y": {"fund": 13.5, "benchmark": 12.6, "category": 13.3}},
           "allocation": {"stocks": 90.3, "bonds": 0, "cash": 9.7, "other": 0}, "top10": [{"name": "A Co", "pct": 2.5}],
           "top10_pct": 18.66, "equity_holdings": 127, "expense_ratio": 0.72, "net_assets_cr": 30677.53,
           "manager": "Mayank Hyanki", "rating_stars": None}
    rep.update(kw)
    return rep


def test_morningstar_report_is_stored_once_and_cross_checked(mfuser):
    import mf
    from db.models import MfReport
    c, uid = mfuser
    with scoped(uid) as s:
        mf.import_payload(s, payload("2026-09", [fund("ZZ Ms Small Cap Fund", aum_cr=30677.53, ter_pct=0.72, top10_pct=25.0,
                                                      managers=[{"name": "Mayank Hyanki", "since": "2024-01-01"}])]))
        mf.import_report(s, morningstar_report(), "morningstarreport1.pdf", "sha-1")
        mf.import_report(s, morningstar_report(expense_ratio=0.73), "morningstarreport1.pdf", "sha-1", b"%PDF-1.4 ms")   # same fund + date: replaced
        s.commit()
        assert s.query(MfReport).filter(MfReport.scheme == "ZZ Ms Small Cap Fund Direct Growth").count() == 1
        with pytest.raises(ValueError):
            mf.import_report(s, {"fund": "", "report_date": ""}, "bad.pdf")
    f = next(x for x in c.get(f"{API}/mf/analysis").json()["funds"] if x["name"] == "ZZ Ms Small Cap Fund")
    (r,) = f["reports"]
    assert r["month"] == "2026-09" and r["compared_month"] == "2026-09"
    st = {ch["metric"]: ch["status"] for ch in r["checks"]}
    assert st["AUM (₹ cr)"] == "ok" and st["Expense ratio %"] == "ok" and st["Top-10 holdings %"] == "differs"
    assert st["Sharpe"] == "info" and st["Fund manager"] == "ok"
    assert r["has_pdf"] is True                      # the PDF itself is kept, so the file can be deleted
    got = c.get(f"{API}/mf/reports/{r['id']}/pdf")
    assert got.status_code == 200 and got.content == b"%PDF-1.4 ms" and got.headers["content-type"] == "application/pdf"
    assert c.get(f"{API}/mf/reports/999999/pdf").status_code == 404


def test_delete_imported_removes_only_files_the_database_holds(mfuser, tmp_path):
    import hashlib
    import import_mf
    import mf
    c, uid = mfuser
    (tmp_path / "Edel").mkdir()
    done, todo = tmp_path / "Edel" / "done.pdf", tmp_path / "todo.pdf"
    done.write_bytes(b"%PDF imported")
    todo.write_bytes(b"%PDF not yet")
    (tmp_path / "_extracted").mkdir()
    keep = tmp_path / "_extracted" / "x.pdf"
    keep.write_bytes(b"%PDF imported")
    with scoped(uid) as s:
        p = payload("2026-09", [fund("ZZ Del Fund")], source="done.pdf")
        p["source_sha256"] = hashlib.sha256(b"%PDF imported").hexdigest()
        mf.import_payload(s, p)
        s.commit()
        gone = import_mf.delete_imported(s, tmp_path, log=lambda *a: None)
    assert gone == [done] and not done.exists() and todo.exists() and keep.exists()
