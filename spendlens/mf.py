"""MF Analysis: the extracted-factsheet format, its import into the database, and the analysis the page shows.

Pipeline: AMC files in `factsheets/YYYY-MM/` -> the mf-factsheet-analyst agent (Claude Code, `/mf-factsheets`) reads
them with `mf_extract.py` and writes one JSON per file to `factsheets/_extracted/YYYY-MM/<file stem>.json` in the
format below -> `import_mf.py` validates and loads it -> `GET /mf/analysis` builds the page from the tables.

JSON per source file (every number optional: null = not printed in the file; nothing is estimated):
    {"month": "2026-10", "as_on": "2026-10-31", "source": "HDFC.pdf", "source_sha256": "...", "kind": "factsheet" | "portfolio",
     "amc": "HDFC Mutual Fund",
     "funds": [{
        "scheme": "HDFC Mid-Cap Opportunities Fund", "plan": "Direct", "amfi_code": "118989",
        "category": "Mid Cap", "benchmark": "NIFTY Midcap 150 TRI",
        "aum_cr": 79000.5, "ter_pct": 0.74, "turnover_pct": 18.0,
        "std_dev": 14.2, "beta": 0.88, "sharpe": 1.21, "alpha": 3.1, "treynor": null,
        "top10_pct": 31.5, "cash_pct": 4.2, "cap_mix": {"large": 8.1, "mid": 66.0, "small": 21.7},
        "returns": {"1y": 12.3, "3y": 24.1, "5y": 28.0}, "benchmark_returns": {"1y": 10.1, "3y": 22.0, "5y": 26.5},
        "debt": {"ytm": null, "mod_duration": null, "avg_maturity": null, "macaulay": null, "aaa_sov_pct": null},
        "managers": [{"name": "Chirag Setalvad", "since": "2007-06-25"}],
        "holdings": [{"name": "Indian Hotels Co", "isin": "INE053A01029", "pct": 3.9, "qty": 12345678,
                      "sector": "Leisure", "rating": ""}],   # qty = shares, when the disclosure prints them
        "notes": "anything the agent could not read or had to leave out"
     }]}

A factsheet (ratios) and a portfolio disclosure (holdings) for the same fund and month merge into one row: a later
file fills or overwrites only the fields it prints, and replaces the holdings only when it lists them.

Buying trend: holdings are compared between factsheets (month to month, and over each year). With share counts the
change is real buying or selling; without them only the weight (% of the fund) is compared, which also moves with the
stock's price, so those rows are marked basis "weight".
"""
import json
import math
import re
from collections import defaultdict
from datetime import date

from db.models import EquityTrade, Holding, MfFundMonth, MfHolding, MfReport, MfSource

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
NUM_FIELDS = {  # json key -> (column, low, high): a value outside the range is a reading mistake
    "aum_cr": ("aum_cr", 0, 1e7), "ter_pct": ("ter_pct", 0, 3.5), "turnover_pct": ("turnover_pct", 0, 2000),
    "std_dev": ("std_dev", 0, 80), "beta": ("beta", -1, 3), "sharpe": ("sharpe", -5, 10), "alpha": ("alpha", -60, 60),
    "treynor": ("treynor", -100, 100), "top10_pct": ("top10_pct", 0, 100), "cash_pct": ("cash_pct", -30, 100),
}
NESTED = {
    "cap_mix": {"large": ("cap_large", 0, 100), "mid": ("cap_mid", 0, 100), "small": ("cap_small", 0, 100)},
    "returns": {"1y": ("ret_1y", -95, 500), "3y": ("ret_3y", -80, 200), "5y": ("ret_5y", -80, 200)},
    "benchmark_returns": {"1y": ("bench_1y", -95, 500), "3y": ("bench_3y", -80, 200), "5y": ("bench_5y", -80, 200)},
    "debt": {"ytm": ("ytm", 0, 25), "mod_duration": ("mod_duration", 0, 40), "avg_maturity": ("avg_maturity", 0, 50),
             "macaulay": ("macaulay", 0, 40), "aaa_sov_pct": ("credit_aaa_sov_pct", 0, 100)},
}
CASH_LINE = re.compile(r"treps|tri-?party|reverse repo|\brepo\b|\btrp_|\brep\d*_|net current|cash|call money|net receivable|"
                       r"margin money|net payable|clearing corporation", re.I)
# Categories whose stock positions are hedged or absent: left out of overlap and of "being bought / sold".
NOT_EQUITY = re.compile(r"debt|liquid|overnight|money market|arbitrage|bond|gilt|duration|credit|fund of funds|fof", re.I)
RATING_RANK = ["SOV", "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB", "B", "C", "D"]


def rating_rank(rating):
    """Position in RATING_RANK (0 = sovereign, higher = worse) for 'CRISIL AA+', 'ICRA AA-', 'SOVEREIGN', ...; None if unknown."""
    r = re.sub(r"\b(CRISIL|ICRA|CARE|IND|FITCH|BRICKWORK|ACUITE|INFOMERICS|\(CE\)|\(SO\))\b", " ", rating.upper())
    r = r.replace("SOVEREIGN", "SOV").replace("(", " ").replace(")", " ").split()
    tok = r[0] if r else ""
    best = max((x for x in RATING_RANK if tok.startswith(x)), key=len, default=None)
    return RATING_RANK.index(best) if best and best == tok else None


# ---------------------------------------------------------------- identity and validation

def scheme_key(scheme, plan=""):
    s = (scheme or "").lower()
    s = re.sub(r"\(?\s*folio\b[^)]*\)?", " ", s)   # "(Folio: 12345678)": several folios are one fund
    s = re.sub(r"\b(fund|scheme|plan|option|growth|direct|regular|idcw|dividend|the)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    p = (plan or "").strip().lower()
    p = "direct" if p.startswith("dir") else "regular" if p.startswith("reg") else p
    return " ".join(s.split()) + (f"|{p}" if p else "")


def _tokens(text):
    return set(scheme_key(text).split("|")[0].split())


def validate(payload):
    """(errors, warnings) for one extracted file. Errors stop the import; warnings are shown and kept."""
    errors, warnings = [], []
    if not isinstance(payload, dict):
        return ["the file is not a JSON object"], []
    if not MONTH.match(str(payload.get("month", ""))):
        errors.append("month must be YYYY-MM")
    as_on = str(payload.get("as_on") or "")
    if as_on and not (re.match(r"^\d{4}-\d{2}-\d{2}$", as_on) and as_on[:7] == payload.get("month")):
        errors.append("as_on must be YYYY-MM-DD within the month")
    if not str(payload.get("source", "")).strip():
        errors.append("source (the factsheet file name) is required")
    if payload.get("kind", "factsheet") not in ("factsheet", "portfolio"):
        errors.append("kind must be factsheet or portfolio")
    funds = payload.get("funds")
    if not isinstance(funds, list) or not funds:
        errors.append("funds must be a non-empty list")
        return errors, warnings
    seen = set()
    for i, f in enumerate(funds):
        where = f"funds[{i}]"
        if not isinstance(f, dict) or not str(f.get("scheme", "")).strip():
            errors.append(f"{where}: scheme name is required")
            continue
        where = f"{f['scheme']}"
        k = scheme_key(f["scheme"], f.get("plan", ""))
        if k in seen:
            errors.append(f"{where}: listed twice")
        seen.add(k)
        checks = [(key, f.get(key), rng) for key, rng in NUM_FIELDS.items()]
        for group, fields in NESTED.items():
            sub = f.get(group) or {}
            if not isinstance(sub, dict):
                errors.append(f"{where}: {group} must be an object")
                continue
            checks += [(f"{group}.{k2}", sub.get(k2), rng) for k2, rng in fields.items()]
        for key, v, (_, lo, hi) in checks:
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
                errors.append(f"{where}: {key} must be a number or null, got {v!r}")
            elif not lo <= v <= hi:
                errors.append(f"{where}: {key} = {v} is outside {lo}..{hi} (a misread figure?)")
        cm = f.get("cap_mix") or {}
        if all(isinstance(cm.get(x), (int, float)) for x in ("large", "mid", "small")) and sum(cm[x] for x in ("large", "mid", "small")) > 105:
            errors.append(f"{where}: cap_mix adds up to more than 100%")
        hs = f.get("holdings") or []
        if not isinstance(hs, list):
            errors.append(f"{where}: holdings must be a list")
            continue
        total = 0.0
        for h in hs:
            if not isinstance(h, dict) or not str(h.get("name", "")).strip() or not isinstance(h.get("pct"), (int, float)):
                errors.append(f"{where}: every holding needs a name and a numeric pct")
                break
            q = h.get("qty")
            if q is not None and (isinstance(q, bool) or not isinstance(q, (int, float)) or q < 0):
                errors.append(f"{where}: {h['name']}: qty must be a non-negative number or null")
                break
            total += h["pct"]
        if hs and total > 105:
            errors.append(f"{where}: holdings add up to {total:.1f}% of the fund")
        elif hs and total < 85:
            warnings.append(f"{where}: holdings cover only {total:.1f}% of the fund (top holdings only?)")
        if f.get("ter_pct") is None and payload.get("kind", "factsheet") == "factsheet":
            warnings.append(f"{where}: no expense ratio")
    return errors, warnings


# ---------------------------------------------------------------- import

def _derived(f):
    """top-10 and cash shares from the holdings when the file doesn't print them."""
    hs = f.get("holdings") or []
    out = {}
    if hs:
        cash = [h for h in hs if CASH_LINE.search(h["name"])]
        # the top 10 positions: single lines, not "Other Domestic Equity (less than 0.50%)" buckets or index futures
        stocks = sorted((h["pct"] for h in hs if h not in cash and not OTHERS_BUCKET.search(h["name"])), reverse=True)
        if f.get("top10_pct") is None and stocks:
            out["top10_pct"] = round(sum(stocks[:10]), 2)
        if f.get("cash_pct") is None and cash:
            out["cash_pct"] = round(sum(h["pct"] for h in cash), 2)
    return out


def import_payload(session, payload, file_name=None):
    """Validate and load one extracted file. Returns {source, month, funds, warnings}; raises ValueError on errors."""
    errors, warnings = validate(payload)
    if errors:
        raise ValueError("; ".join(errors[:8]) + (f" (+{len(errors) - 8} more)" if len(errors) > 8 else ""))
    month, name = payload["month"], file_name or payload["source"]
    src = session.query(MfSource).filter(MfSource.month == month, MfSource.file_name == name).first()
    if src is None:
        src = MfSource(month=month, file_name=name)
        session.add(src)
    src.sha256 = payload.get("source_sha256", "") or ""
    src.as_on = str(payload.get("as_on") or "")
    src.kind = payload.get("kind", "factsheet")
    src.amc = (payload.get("amc") or "").strip()
    src.funds = len(payload["funds"])
    src.notes = "; ".join(warnings)[:2000]
    session.flush()
    for f in payload["funds"]:
        key = scheme_key(f["scheme"], f.get("plan", ""))
        code = str(f.get("amfi_code") or "").strip()
        # the same fund and month is one row: by AMFI code first (names differ slightly between an AMC's PDF and Excel)
        row = (session.query(MfFundMonth).filter(MfFundMonth.amfi_code == code, MfFundMonth.month == month).first() if code else None) \
            or session.query(MfFundMonth).filter(MfFundMonth.scheme_key == key, MfFundMonth.month == month).first()
        if row is None:
            row = MfFundMonth(scheme_key=key, month=month, scheme=f["scheme"].strip())
            session.add(row)
        for attr in ("plan", "amfi_code", "category", "benchmark", "notes"):
            if str(f.get(attr) or "").strip():
                setattr(row, attr, str(f[attr]).strip())
        if src.amc:
            row.amc = src.amc
        if src.as_on:
            row.as_on = src.as_on
        session.flush()
        existing = session.query(MfHolding).filter(MfHolding.fund_month_id == row.id)
        # a portfolio disclosure (every line, with share counts) wins over a factsheet's list, whatever the order;
        # top-10 and cash worked out from holdings then come only from the holdings that are kept
        keep = src.kind == "factsheet" and existing.filter(MfHolding.qty.isnot(None)).first() is not None
        vals = {**{k: f.get(k) for k in NUM_FIELDS}, **({} if keep else _derived(f))}
        for k, v in vals.items():
            if v is not None:
                setattr(row, NUM_FIELDS[k][0], float(v))
        for group, fields in NESTED.items():
            sub = f.get(group) or {}
            for k2, (col, _, _) in fields.items():
                if sub.get(k2) is not None:
                    setattr(row, col, float(sub[k2]))
        if f.get("managers"):
            mgrs = [{"name": str(m.get("name", "")).strip(), "since": str(m.get("since") or "")}
                    for m in f["managers"] if isinstance(m, dict) and m.get("name")]
            row.managers = json.dumps(mgrs)
            row.fund_manager = ", ".join(m["name"] for m in mgrs)
        row.source_id = src.id
        session.flush()
        if f.get("holdings") and not keep:
            existing.delete(synchronize_session=False)
            for h in f["holdings"]:
                session.add(MfHolding(fund_month_id=row.id, name=str(h["name"]).strip(), isin=str(h.get("isin") or "").strip().upper(),
                                      pct=float(h["pct"]), sector=str(h.get("sector") or "").strip(), rating=str(h.get("rating") or "").strip().upper(),
                                      qty=float(h["qty"]) if h.get("qty") is not None else None))
    session.flush()
    return {"source": name, "month": month, "funds": len(payload["funds"]), "warnings": warnings}


# ---------------------------------------------------------------- analysis

def _match(holdings, schemes):
    """{holding id: scheme_key} by AMFI code first, then by name (most shared words, at least 60% of the shorter name)."""
    by_code = {s["amfi_code"]: k for k, s in schemes.items() if s["amfi_code"]}
    out = {}
    for h in holdings:
        if h.scheme_code and h.scheme_code in by_code:
            out[h.id] = by_code[h.scheme_code]
            continue
        ht = _tokens(h.name)
        direct = "direct" in h.name.lower()
        best, score = None, 0.0
        for k, s in schemes.items():
            st = _tokens(s["scheme"])
            if not ht or not st:
                continue
            sc = len(ht & st) / min(len(ht), len(st))
            plan = k.split("|")[1] if "|" in k else ""
            sc += 0.05 if (plan == "direct") == direct else 0
            if sc > score:
                best, score = k, sc
        if best and score >= 0.6:
            out[h.id] = best
    return out


def _since_years(managers, month):
    yrs = []
    for m in managers:
        try:
            yrs.append((date.fromisoformat(month + "-28") - date.fromisoformat(m["since"][:10])).days / 365.25)
        except (ValueError, KeyError, TypeError):
            pass
    return round(max(yrs), 1) if yrs else None


MATURITY = re.compile(r"\(\s*\d{1,2}/\d{1,2}/\d{2,4}\s*\)|\b(cd|cp|t-?bill|ncd|sdl|gsec|g-sec|debenture|bond|commercial paper|certificate of deposit)\b", re.I)
# "Other Domestic Equity (Less than 0.50% of the corpus)": many small positions in one line, not a stock
OTHERS_BUCKET = re.compile(r"\bother\b.*\b(equity|holdings|securities)\b|less than [\d.]+\s*% of"
                           r"|^(NIFTY|BANKNIFTY|FINNIFTY|SENSEX)\b|\b(futures?|options?|index derivatives?)\b", re.I)   # and index derivatives
EQUITY_TYPES = {"01", "02", "23", "25"}   # ISIN security-type digits: equity shares (01, partly paid 02), InvIT / REIT units


def is_stock(h):
    """Equity-like lines (shares, REIT / InvIT units, foreign shares), not debt, money market, fund units or cash:
    CDs, CPs and T-bills mature and roll every month, so they would swamp the buying trend."""
    if CASH_LINE.search(h.name) or (h.rating or "").strip() or MATURITY.search(h.name) or OTHERS_BUCKET.search(h.name):
        return False
    isin = (h.isin or "").upper()
    if not isin:
        return True
    if isin.startswith("INF") or re.match(r"^IN\d", isin):   # fund units; government securities and T-bills
        return False
    if isin.startswith("IN"):
        return isin[7:9] in EQUITY_TYPES
    return True                                               # foreign shares (US..., etc.)


def _ckey(h):
    """A stock's identity across months: its ISIN issuer code for Indian shares (a face-value split gives the shares
    a new ISIN, e.g. Kotak's 5:1 in 2026), else the ISIN, else the name."""
    isin = (h.isin or "").upper()
    if isin.startswith("IN") and not isin.startswith("INF") and isin[7:9] in EQUITY_TYPES:
        return isin[:7] + ("U" if isin[7:9] in ("23", "25") else "E")
    return isin or re.sub(r"[^a-z0-9]+", " ", h.name.lower()).strip()


def analysis(session, today=None):
    rows = session.query(MfFundMonth).order_by(MfFundMonth.month).all()
    known = known_actions(session)
    sources = session.query(MfSource).order_by(MfSource.month).all()
    held = [h for h in session.query(Holding).filter(Holding.asset_type == "MF").all() if h.visible != 0]
    by_key = defaultdict(list)
    for r in rows:
        by_key[r.scheme_key].append(r)
    schemes = {k: {"scheme": v[-1].scheme, "amfi_code": v[-1].amfi_code} for k, v in by_key.items()}
    matched = _match(held, schemes)
    value_of = defaultdict(float)
    for h in held:
        if h.id in matched:
            value_of[matched[h.id]] += (h.qty or 0) * (h.cmp or 0)
    hold_ids = defaultdict(list)
    fm_ids = [r.id for r in rows]
    for hh in (session.query(MfHolding).filter(MfHolding.fund_month_id.in_(fm_ids)).all() if fm_ids else []):
        hold_ids[hh.fund_month_id].append(hh)

    funds, anomalies = [], []
    reps = reports(session, by_key)
    for key, ms in by_key.items():
        last = ms[-1]
        months = [m.month for m in ms]
        mgrs = json.loads(last.managers) if last.managers else []

        def series(col):
            return [{"month": m.month, "value": getattr(m, col)} for m in ms if getattr(m, col) is not None]
        latest = {
            "ret1y": last.ret_1y, "ret3y": last.ret_3y, "ret5y": last.ret_5y,
            "vsBench3y": round(last.ret_3y - last.bench_3y, 2) if last.ret_3y is not None and last.bench_3y is not None else None,
            "alpha": last.alpha, "stdDev": last.std_dev, "beta": last.beta, "sharpe": last.sharpe, "treynor": last.treynor,
            "ter": last.ter_pct, "aum": last.aum_cr, "turnover": last.turnover_pct, "top10": last.top10_pct, "cash": last.cash_pct,
            "ytm": last.ytm, "modDuration": last.mod_duration, "avgMaturity": last.avg_maturity, "credit": last.credit_aaa_sov_pct,
            # need NAV / benchmark history, not in factsheets: computed in a later step
            "rollingBeat": None, "sortino": None, "downCapture": None, "upCapture": None, "maxDD": None,
        }
        funds.append({
            "key": key, "name": last.scheme, "plan": last.plan, "amc": last.amc, "amfi_code": last.amfi_code,
            "category": last.category, "benchmark": last.benchmark, "held": key in value_of, "value": round(value_of.get(key, 0), 2),
            "months": months, "latest_month": last.month, "latest": latest,
            "series": {"ter": series("ter_pct"), "aum": series("aum_cr"), "beta": series("beta"), "sharpe": series("sharpe"),
                       "top10": series("top10_pct"), "cash": series("cash_pct"), "rolling3y": series("ret_3y")},
            "manager": last.fund_manager or ", ".join(m["name"] for m in mgrs), "manager_years": _since_years(mgrs, last.month),
            "managers": mgrs, "as_on": last.as_on,
            "cap_mix": {"large": last.cap_large, "mid": last.cap_mid, "small": last.cap_small},
            "holdings_count": len(hold_ids.get(last.id, [])),
            "trends": holding_trends(ms, hold_ids, known),
            "reports": reps.get(key, []),
        })
        anomalies += _anomalies(ms, hold_ids)

    overlap = _overlap(funds, by_key, hold_ids)

    all_months = sorted({s.month for s in sources})[-6:]
    by_amc = defaultdict(set)
    for s in sources:
        by_amc[s.amc or s.file_name].add(s.month)
    coverage = [{"amc": amc, "months": [{"month": m, "loaded": m in ms} for m in all_months]} for amc, ms in sorted(by_amc.items())]
    unmatched, seen = [], set()   # one line per scheme, however many folios hold it
    for h in held:
        k = scheme_key(h.name)
        if h.id not in matched and k not in seen:
            seen.add(k)
            unmatched.append({"name": h.name, "scheme_code": h.scheme_code or ""})
    rank = {"high": 0, "medium": 1, "low": 2}
    return {
        "has_data": bool(rows), "funds": sorted(funds, key=lambda f: (not f["held"], -f["value"], f["name"])),
        "anomalies": sorted(anomalies, key=lambda a: (rank[a["severity"]], a["fund"])),
        "overlap": overlap, "coverage": coverage, "unmatched_holdings": unmatched,
        "market_moves": market_moves(funds),
        "latest_month": max((r.month for r in rows), default=None),
        "sources": [{"month": s.month, "file": s.file_name, "kind": s.kind, "amc": s.amc, "funds": s.funds, "notes": s.notes,
                     "imported_at": s.imported_at} for s in reversed(sources)][:100],
    }


NAME_NOISE = re.compile(r"\b(the|ltd|limited|co|company|corp|corporation|inc|plc|class [a-z]|of india)\b")


def stock_name_key(name):
    """'The Federal Bank Ltd' and 'Federal Bank Limited' -> 'federal bank': for matching a factsheet line without an ISIN
    (Axis, Edelweiss print names only) to a disclosure line with one."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(NAME_NOISE.sub(" ", s).split())


def _overlap(funds, by_key, hold_ids):
    """Common holdings % between each pair of held equity funds (latest month of each): the sum over shared stocks of
    the smaller weight. Stocks are matched by ISIN issuer, or by name when a factsheet prints no ISIN. When a fund's
    lines cover well under 100% (a factsheet with only its top 10), the figure is a lower bound: `partial`."""
    eq = [f for f in funds if f["held"] and not NOT_EQUITY.search(f["category"] or "")]
    lines = {f["key"]: hold_ids.get(by_key[f["key"]][-1].id, []) for f in eq}
    by_name = {}                                     # name key -> issuer key, from every line that has an ISIN
    for rows in lines.values():
        for h in rows:
            if (h.isin or "").strip() and is_stock(h):
                by_name.setdefault(stock_name_key(h.name), _ckey(h))
    snaps = {}
    for k, rows in lines.items():
        snap = {}
        for ck, line in _snapshot(rows).items():
            key = ck if (line.isin or "").strip() else by_name.get(stock_name_key(line.name), "n:" + stock_name_key(line.name))
            if key in snap:
                snap[key].pct += line.pct
            else:
                snap[key] = line
        snaps[k] = snap
    cover = {k: sum(h.pct for h in rows) for k, rows in lines.items()}
    out = []
    for i in range(len(eq)):
        for j in range(i + 1, len(eq)):
            a, b = snaps[eq[i]["key"]], snaps[eq[j]["key"]]
            if not a or not b:
                continue
            common = sorted(((min(a[k].pct, b[k].pct), a[k].name) for k in set(a) & set(b)), reverse=True)
            out.append({"a": eq[i]["name"], "b": eq[j]["name"], "pct": round(sum(p for p, _ in common), 1),
                        "shared": [n for _, n in common[:3]], "count": len(common),
                        "partial": min(cover[eq[i]["key"]], cover[eq[j]["key"]]) < 80})
    return out


def import_report(session, rep, file_name="", sha256="", pdf=None):
    """Store one parsed Morningstar report (mf_parsers.parse_morningstar) for cross-checking. Replaces the row for the
    same fund and report date. Returns the scheme_key it was filed under."""
    if not rep.get("fund") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(rep.get("report_date") or "")):
        raise ValueError(f"{file_name}: not a Morningstar fund report (no fund name or report date)")
    name = rep["fund"]
    key = scheme_key(name, "Direct" if re.search(r"\bdirect\b", name, re.I) else "Regular")
    month = (rep.get("portfolio_date") or "")[:7]
    row = session.query(MfReport).filter(MfReport.source == "morningstar", MfReport.scheme_key == key,
                                         MfReport.report_date == rep["report_date"]).first()
    if row is None:
        row = MfReport(source="morningstar", scheme_key=key, report_date=rep["report_date"], scheme=name)
        session.add(row)
    row.scheme, row.isin, row.month = name, rep.get("isin") or "", month
    row.data, row.file_name, row.sha256 = json.dumps(rep), file_name, sha256
    if pdf is not None:
        row.pdf = pdf
    session.flush()
    return key


# AMC figure vs Morningstar's: (label, factsheet value, Morningstar value, unit, tolerance, note). Ratios are computed on
# different windows and risk-free rates by each, so a gap there is expected; holdings-based figures should agree.
def _cross_check(fm, rep):
    r = rep.get("risk") or {}
    t = rep.get("trailing") or {}
    alloc = rep.get("allocation") or {}
    rows = [
        ("AUM (₹ cr)", fm.aum_cr if fm else None, rep.get("net_assets_cr"), "", 2.0, "same month-end: should match"),
        ("Expense ratio %", fm.ter_pct if fm else None, rep.get("expense_ratio"), "%", 0.05,
         "Direct plan. PPFAS and Edelweiss print the base expense ratio (before GST and other charges); Morningstar the total"),
        ("Top-10 holdings %", fm.top10_pct if fm else None, rep.get("top10_pct"), "%", 1.5, ""),
        ("Cash & equivalents %", fm.cash_pct if fm else None, alloc.get("cash"), "%", None,
         "Morningstar also counts money-market and hedged (arbitrage) positions as cash"),
        ("Std deviation", fm.std_dev if fm else None, r.get("std_dev"), "", None, "different windows (AMC often 1y or 3y monthly)"),
        ("Beta", fm.beta if fm else None, r.get("beta"), "", None, "against each one's benchmark"),
        ("Sharpe", fm.sharpe if fm else None, r.get("sharpe"), "", None, "different risk-free rates"),
        ("3y return %", fm.ret_3y if fm else None, (t.get("3y") or {}).get("fund"), "%", None, "Morningstar to the report date"),
        ("5y return %", fm.ret_5y if fm else None, (t.get("5y") or {}).get("fund"), "%", None, "Morningstar to the report date"),
    ]
    out = []
    for label, a, b, unit, tol, note in rows:
        if a is None and b is None:
            continue
        diff = round(b - a, 2) if a is not None and b is not None else None
        if diff is None:
            status = "missing"
        elif tol is None:
            status = "info"
        else:
            rel = abs(diff) / abs(a) * 100 if label.startswith("AUM") and a else abs(diff)
            status = "ok" if rel <= tol else "differs"
        out.append({"metric": label, "factsheet": a, "morningstar": b, "diff": diff, "status": status, "note": note})
    mgr = rep.get("manager") or ""
    if mgr:
        names = (fm.fund_manager or "") if fm else ""
        ok = any(w and w.lower() in names.lower() for w in mgr.split()[-1:])
        out.append({"metric": "Fund manager", "factsheet": names or None, "morningstar": mgr, "diff": None,
                    "status": "ok" if ok else ("missing" if not names else "differs"), "note": "Morningstar lists the lead manager"})
    return out


def reports(session, by_key):
    """{scheme_key: [report, ...]} newest first, each with the cross-check against the factsheet month of its portfolio
    date (else the nearest earlier month we have)."""
    out = defaultdict(list)
    with_pdf = {i for (i,) in session.query(MfReport.id).filter(MfReport.pdf.isnot(None)).all()}
    for row in session.query(MfReport).order_by(MfReport.report_date.desc()).all():
        rep = json.loads(row.data or "{}")
        ms = by_key.get(row.scheme_key, [])
        fm = next((m for m in reversed(ms) if m.month <= (row.month or "9999")), None)
        out[row.scheme_key].append({
            "id": row.id, "source": row.source, "scheme": row.scheme, "report_date": row.report_date, "month": row.month,
            "compared_month": fm.month if fm else None, "file": row.file_name, "has_pdf": row.id in with_pdf,
            "rating_stars": rep.get("rating_stars"), "risk": rep.get("risk") or {}, "trailing": rep.get("trailing") or {},
            "allocation": rep.get("allocation") or {}, "top10": rep.get("top10") or [], "equity_holdings": rep.get("equity_holdings"),
            "manager": rep.get("manager") or "", "net_assets_cr": rep.get("net_assets_cr"), "expense_ratio": rep.get("expense_ratio"),
            "checks": _cross_check(fm, rep),
        })
    return out


def report_pdf(session, report_id):
    """(file name, PDF bytes) of a stored report of the session's user, or None."""
    row = session.query(MfReport).filter(MfReport.id == report_id).first()
    return (row.file_name or f"report-{row.id}.pdf", row.pdf) if row is not None and row.pdf else None


def _anomalies(ms, hold_ids):
    """The rules of mfMetrics.ANOMALY_RULES, on the latest month against the earlier ones."""
    out = []
    last = ms[-1]
    prev = ms[-2] if len(ms) > 1 else None
    back3 = ms[-4] if len(ms) > 3 else ms[0] if len(ms) > 1 else None
    name, m = last.scheme, last.month

    def add(sev, rule, detail):
        out.append({"severity": sev, "month": m, "fund": name, "rule": rule, "detail": detail})
    if prev:
        a = {x["name"] for x in (json.loads(prev.managers) if prev.managers else [])}
        b = {x["name"] for x in (json.loads(last.managers) if last.managers else [])}
        if a and b and a != b:
            add("high", "Fund manager changed", f"{', '.join(sorted(a)) or '—'} → {', '.join(sorted(b))}.")
        if prev.ter_pct is not None and last.ter_pct is not None and last.ter_pct - prev.ter_pct >= 0.1:
            add("medium", "Expense ratio up", f"TER {prev.ter_pct:.2f}% → {last.ter_pct:.2f}%.")
        if prev.aum_cr and last.aum_cr and last.aum_cr <= prev.aum_cr * 0.85:
            add("medium", "AUM fell sharply", f"₹{prev.aum_cr:,.0f} cr → ₹{last.aum_cr:,.0f} cr in a month.")
    if back3 and back3 is not last:
        for col, label in (("beta", "Beta"), ("std_dev", "Standard deviation")):
            x0, x1 = getattr(back3, col), getattr(last, col)
            if x0 and x1 and x1 > x0 * 1.2:
                add("low", f"{label} jumped", f"{label} {x0:.2f} → {x1:.2f} since {back3.month}.")
        if back3.top10_pct is not None and last.top10_pct is not None and last.top10_pct - back3.top10_pct >= 10:
            add("low", "More concentrated", f"Top-10 holdings {back3.top10_pct:.0f}% → {last.top10_pct:.0f}% since {back3.month}.")
    earlier_cash = [x.cash_pct for x in ms[:-1][-12:] if x.cash_pct is not None]
    if earlier_cash and last.cash_pct is not None:
        avg = sum(earlier_cash) / len(earlier_cash)
        if last.cash_pct >= 5 and avg > 0 and last.cash_pct >= 2 * avg:
            add("medium", "Cash pile-up", f"Cash {last.cash_pct:.1f}%, {last.cash_pct / avg:.1f}× its average.")
    cat = (last.category or "").lower()
    for word, col, floor in (("large", "cap_large", 80), ("mid", "cap_mid", 65), ("small", "cap_small", 65)):
        v = getattr(last, col)
        if f"{word} cap" in cat and "&" not in cat and v is not None and v < floor:
            add("high", "Outside its mandate", f"{word.title()} caps {v:.0f}% (SEBI minimum {floor}% for a {word}-cap fund).")
    lag = [x for x in ms[-6:] if x.ret_3y is not None and x.bench_3y is not None]
    if len(lag) == 6 and all(x.ret_3y < x.bench_3y for x in lag):
        add("medium", "Lagging its benchmark", "3-year return below the benchmark in each of the last 6 factsheets.")
    if prev:
        before = {h.isin: h.rating for h in hold_ids.get(prev.id, []) if h.isin and h.rating}
        for h in hold_ids.get(last.id, []):
            r0, r1 = before.get(h.isin), h.rating
            if r0 and r1:
                k0, k1 = rating_rank(r0), rating_rank(r1)
                if k0 is not None and k1 is not None and k1 > k0:
                    add("high", "Credit downgrade", f"{h.name}: {r0} → {r1} ({h.pct:.1f}% of the fund).")
    return out


# ---------------------------------------------------------------- buying trend

STATUS_ORDER = {"new": 0, "added": 1, "trimmed": 2, "exited": 3, "held": 4}
QTY_MOVE = 1.0      # % change in shares that counts as buying / selling
WEIGHT_MOVE = 0.25  # percentage points of the fund, when there are no share counts


class _Line:
    """Several lines of one stock in a month (e.g. a core and an 'arbitrage' position) added together."""
    def __init__(self, h):
        self.name, self.isin, self.sector, self.rating = h.name, h.isin, h.sector, h.rating
        self.pct, self.qty = h.pct, h.qty

    def add(self, h):
        self.pct += h.pct
        self.qty = None if self.qty is None or h.qty is None else self.qty + h.qty


def _snapshot(rows, stocks_only=True):
    out = {}
    for h in rows:
        if CASH_LINE.search(h.name) or (stocks_only and not is_stock(h)):
            continue
        k = _ckey(h)
        if k in out:
            out[k].add(h)
        else:
            out[k] = _Line(h)
    return out


SPLIT_RATIOS = (2, 2.5, 4, 5, 10)        # face-value splits (the ISIN changes)
BONUS_RATIOS = (2,)                      # 1:1 bonus (the ISIN stays); rarer ratios are indistinguishable from buying


def _step_factor(x, y):
    """A split or bonus between two consecutive factsheets of one stock, else None.
    A face-value split always gives the shares a new ISIN: then the factor is the clean ratio that best reconciles
    the share count with the weight. A bonus keeps the ISIN: only shares exactly doubled (within 2%) with the
    weight nearly unchanged (within 15%) over the one month counts. Buying never looks like that."""
    if not x.qty or not y.qty or not x.pct or not y.pct:
        return None
    r, wr = y.qty / x.qty, y.pct / x.pct
    if x.isin and y.isin and x.isin != y.isin:
        if abs(math.log(r / wr)) < math.log(1.5):
            return None
        f = min(SPLIT_RATIOS, key=lambda f: abs(math.log((r / f) / wr)))
        return f if abs(math.log((r / f) / wr)) < math.log(1.35) else None
    if abs(math.log(wr)) < math.log(1.15):
        return next((f for f in BONUS_RATIOS if abs(r / f - 1) < 0.02), None)
    return None


def _step_events(snaps):
    """{(stock key, index): factor} for every split / bonus between snaps[index-1] and snaps[index]."""
    ev = {}
    for i in range(1, len(snaps)):
        a, b = snaps[i - 1][1], snaps[i][1]
        for k in set(a) & set(b):
            f = _step_factor(a[k], b[k])
            if f:
                ev[(k, i)] = f
    return ev


def diff_holdings(a, b, frm, to, factors=None):
    """Position changes from snapshot a (month frm) to b (month to). factors: {stock key: split / bonus factor
    between the two} so share counts are compared like for like."""
    factors = factors or {}
    out = []
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        h = y or x
        qa, qb = (x.qty if x else None), (y.qty if y else None)
        basis = "shares" if (x is None or qa is not None) and (y is None or qb is not None) and (qa or qb) else "weight"
        wa, wb = (x.pct if x else 0.0), (y.pct if y else 0.0)
        split = factors.get(k) if basis == "shares" and x is not None and y is not None else None
        qa_adj = qa * split if split else qa
        qchg = round((qb - qa_adj) / qa_adj * 100, 1) if basis == "shares" and qa_adj and qb is not None else None
        if x is None:
            status = "new"
        elif y is None:
            status = "exited"
        elif basis == "shares":
            status = "added" if qchg is not None and qchg >= QTY_MOVE else "trimmed" if qchg is not None and qchg <= -QTY_MOVE else "held"
        else:
            status = "added" if wb - wa >= WEIGHT_MOVE else "trimmed" if wb - wa <= -WEIGHT_MOVE else "held"
        out.append({"stock": h.name, "isin": h.isin, "sector": h.sector, "status": status, "basis": basis,
                    "from_pct": round(wa, 2) if x else None, "to_pct": round(wb, 2) if y else None,
                    "weight_change": round(wb - wa, 2), "from_qty": qa, "to_qty": qb, "qty_change_pct": qchg,
                    "note": f"split / bonus ×{split:g}: shares compared after adjusting" if split else ""})
    out.sort(key=lambda r: (STATUS_ORDER[r["status"]],
                            -abs(r["qty_change_pct"] if r["qty_change_pct"] is not None else r["weight_change"] * 10)))
    counts = {st: sum(1 for r in out if r["status"] == st) for st in STATUS_ORDER}
    basis = None
    if out:
        basis = "shares" if all(r["basis"] == "shares" for r in out) else "weight"
    return {"from": frm, "to": to, "rows": out, "counts": counts, "basis": basis}


def known_actions(session):
    """{stock key: [(ex_date, factor)]}: market-wide splits and bonuses from the stock ledger's corporate actions
    (Yahoo's split history plus the built-in ones), for every stock the user has traded (their trades give the
    ISIN for each NSE symbol). Detection from the factsheets covers the rest."""
    import equity as eq
    events = eq.all_events(session)
    canon = eq.make_canonical(events)
    by_sym = {}
    for e in events:
        if e["kind"] in ("SPLIT", "BONUS") and not e["account"]:
            by_sym.setdefault(canon(e["symbol"]), []).append((e["ex_date"], eq.factor(e)))
    out = {}
    for isin, sym in session.query(EquityTrade.isin, EquityTrade.symbol).distinct():
        acts = by_sym.get(canon(sym))
        if not acts or not isin:
            continue

        class _H:   # what _ckey needs
            pass
        h = _H()
        h.isin, h.name = isin, sym
        out.setdefault(_ckey(h), sorted(set(acts)))
    return out


def holding_trends(ms, hold_ids, known=None):
    """{years: [{year, from, to, rows, counts, basis}], latest: {...} | None}. A year compares the last factsheet of
    the year before (or the year's first, if there is none) with the year's last."""
    snaps = [(m.month, _snapshot(hold_ids[m.id])) for m in ms if hold_ids.get(m.id)]
    ev = _step_events(snaps)
    # a known split / bonus between two factsheets wins over detection (it also catches a bonus in a month the
    # fund bought more, which detection can't tell apart)
    for k, acts in (known or {}).items():
        for i in range(1, len(snaps)):
            lo, hi = snaps[i - 1][0], snaps[i][0]
            f = 1.0
            for d, fac in acts:
                if lo < d[:7] <= hi:
                    f *= fac
            if f != 1.0 and k in snaps[i - 1][1] and k in snaps[i][1]:
                ev[(k, i)] = f

    def between(i0, i1):
        out = {}
        for (k, i), f in ev.items():
            if i0 < i <= i1:
                out[k] = out.get(k, 1) * f
        return out
    idx = {m: i for i, (m, _) in enumerate(snaps)}
    years = []
    for y in sorted({m[:4] for m, _ in snaps}):
        inside = [(m, s) for m, s in snaps if m[:4] == y]
        before = [(m, s) for m, s in snaps if m[:4] < y]
        start = before[-1] if before else inside[0]
        end = inside[-1]
        if start[0] != end[0]:
            years.append({"year": y, **diff_holdings(start[1], end[1], start[0], end[0], between(idx[start[0]], idx[end[0]]))})
    n = len(snaps)
    latest = diff_holdings(snaps[-2][1], snaps[-1][1], snaps[-2][0], snaps[-1][0], between(n - 2, n - 1)) if n > 1 else None
    return {"years": years, "latest": latest, "months_with_holdings": [m for m, _ in snaps]}


def market_moves(funds):
    """Across your funds (held ones, or all when none is matched): which stocks several of them are buying or selling,
    for the latest change and for each year."""
    pool = [f for f in funds if not NOT_EQUITY.search(f["category"] or "")]
    pool = [f for f in pool if f["held"]] or pool

    def agg(changes):
        by = {}
        for fname, ch in changes:
            for r in ch["rows"]:
                if r["status"] == "held":
                    continue
                k = r["isin"] or r["stock"].lower()
                a = by.setdefault(k, {"stock": r["stock"], "isin": r["isin"], "sector": r["sector"], "buying": [], "selling": [],
                                      "new_in": [], "exited_from": [], "weight_change": 0.0})
                a["weight_change"] = round(a["weight_change"] + r["weight_change"], 2)
                (a["buying"] if r["status"] in ("new", "added") else a["selling"]).append(fname)
                if r["status"] == "new":
                    a["new_in"].append(fname)
                if r["status"] == "exited":
                    a["exited_from"].append(fname)
        rows = list(by.values())
        for a in rows:
            a["net"] = len(a["buying"]) - len(a["selling"])
        rows.sort(key=lambda a: (-a["net"], -a["weight_change"], a["stock"]))
        return rows
    latest = agg([(f["name"], f["trends"]["latest"]) for f in pool if f["trends"]["latest"]])
    years = sorted({y["year"] for f in pool for y in f["trends"]["years"]})
    by_year = {y: agg([(f["name"], t) for f in pool for t in f["trends"]["years"] if t["year"] == y]) for y in years}
    return {"funds": len(pool), "latest": latest, "by_year": by_year}
