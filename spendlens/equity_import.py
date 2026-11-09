"""Reading broker files into the stock ledger: Zerodha Console tradebooks (.xlsx), dividend statements (.csv) and the
holdings statement (.xlsx). Each file is recognised from its contents, not its name.

Imports are idempotent: a trade is keyed by its fingerprint, so re-uploading a file (or two copies of one) adds
nothing. A dividend statement replaces the account's statement rows for the period it covers, and removes any
Yahoo-fetched rows there, because the broker's statement is the record of what was actually paid. Everything an import
changes is written to equity_audit.
"""
import csv
import io
import json
import re
from datetime import date, datetime

import openpyxl

from db.models import BrokerHolding, EquityAudit, EquityDividend, EquityTrade

PERIOD = re.compile(r"from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", re.I)
AS_ON = re.compile(r"as (?:on|of) (\d{4}-\d{2}-\d{2})", re.I)
FILE_PERIOD = re.compile(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})")


class ImportError_(ValueError):
    pass


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


def _num(v):
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "").strip() or 0)


def _iso(v):
    s = _cell(v)[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(_cell(v), fmt).date().isoformat()
            except ValueError:
                pass
    raise ImportError_(f"Unreadable date {v!r}")


def _rows(sheet):
    """Every row with its cells as text-trimmed values (leading blank column kept; callers search by header name)."""
    return [list(r) for r in sheet.iter_rows(values_only=True)]


def _header(rows, must):
    """(index, {header: column}) of the first row containing every name in `must`."""
    for i, r in enumerate(rows):
        names = [_cell(c) for c in r]
        if all(m in names for m in must):
            return i, {n: j for j, n in enumerate(names) if n}
    return None, None


def _meta(rows):
    """Client id, period and as-on date printed above the table."""
    out = {"client_id": "", "period": None, "as_of": None, "title": ""}
    for r in rows[:30]:
        cells = [_cell(c) for c in r if _cell(c)]
        if not cells:
            continue
        if cells[0].lower() == "client id" and len(cells) > 1:
            out["client_id"] = cells[1]
        line = " ".join(cells)
        if m := PERIOD.search(line):
            out["period"] = (m.group(1), m.group(2))
            out["title"] = line
        if m := AS_ON.search(line):
            out["as_of"] = m.group(1)
    return out


def sniff(name, data):
    """'tradebook' / 'holdings' / 'dividends', or raises for anything else."""
    low = name.lower()
    if low.endswith(".csv"):
        head = data[:400].decode("utf-8-sig", "replace")
        if "Dividend per share" in head or "Ex-date" in head:
            return "dividends"
        if "Trade Type" in head and "Trade ID" in head:
            return "tradebook"
        raise ImportError_(f"{name}: not a dividend statement or tradebook")
    if low.endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        for ws in wb.worksheets:
            rows = _rows(ws)
            if _header(rows, ["Symbol", "Trade Type", "Trade ID"])[0] is not None:
                return "tradebook"
            if _header(rows, ["Symbol", "Quantity Available"])[0] is not None:
                return "holdings"
        raise ImportError_(f"{name}: no tradebook or holdings table found")
    raise ImportError_(f"{name}: upload .xlsx or .csv files from Console")


def parse_tradebook(name, data):
    """{client_id, period, trades: [dict]}"""
    if name.lower().endswith(".csv"):
        rows = [r for r in csv.reader(io.StringIO(data.decode("utf-8-sig")))]
    else:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        rows = next((r for r in (_rows(ws) for ws in wb.worksheets) if _header(r, ["Symbol", "Trade Type"])[0] is not None), [])
    meta = _meta(rows)
    i, col = _header(rows, ["Symbol", "Trade Date", "Trade Type", "Quantity", "Price"])
    if i is None:
        raise ImportError_(f"{name}: tradebook header not found")
    trades = []
    for r in rows[i + 1:]:
        g = lambda k: r[col[k]] if k in col and col[k] < len(r) else None  # noqa: E731
        sym = _cell(g("Symbol"))
        if not sym:
            continue
        side = _cell(g("Trade Type")).upper()
        if side not in ("BUY", "SELL"):
            continue
        trades.append({"symbol": sym.upper(), "isin": _cell(g("ISIN")), "trade_date": _iso(g("Trade Date")), "side": side,
                       "qty": _num(g("Quantity")), "price": _num(g("Price")), "exchange": _cell(g("Exchange")),
                       "trade_id": _cell(g("Trade ID")), "order_id": _cell(g("Order ID")),
                       "executed_at": _cell(g("Order Execution Time"))})
    if not meta["period"] and trades:
        ds = sorted(t["trade_date"] for t in trades)
        meta["period"] = (ds[0], ds[-1])
    return {"client_id": meta["client_id"], "period": meta["period"], "trades": trades}


def parse_dividends(name, data):
    """{period, rows: [{raw_symbol, ex_date, qty, dps, amount}]}; the period comes from the Console file name."""
    rd = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    out = []
    for r in rd:
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if not r.get("Symbol") or not r.get("Ex-date"):
            continue
        qty, dps = _num(r.get("Qty")), _num(r.get("Dividend per share"))
        amt = _num(r.get("Total dividend")) or qty * dps
        out.append({"raw_symbol": r["Symbol"].upper(), "ex_date": _iso(r["Ex-date"]), "qty": qty, "dps": dps, "amount": round(amt, 2)})
    m = FILE_PERIOD.search(name)
    if m:
        period = (m.group(1), m.group(2))
    elif out:
        # no period in the name: the Indian financial years spanning the rows
        lo, hi = min(r["ex_date"] for r in out), max(r["ex_date"] for r in out)
        y0 = int(lo[:4]) - (1 if int(lo[5:7]) < 4 else 0)
        y1 = int(hi[:4]) + (0 if int(hi[5:7]) < 4 else 1)
        period = (f"{y0}-04-01", f"{y1}-03-31")
    else:
        raise ImportError_(f"{name}: empty dividend statement with no period in its name")
    return {"period": period, "rows": out}


def parse_holdings(name, data):
    """{client_id, as_of, rows: [{symbol, isin, qty, avg_price}]} from the Console holdings statement (equity sheet)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    for ws in wb.worksheets:
        rows = _rows(ws)
        i, col = _header(rows, ["Symbol", "Quantity Available"])
        if i is None:
            continue
        meta = _meta(rows)
        qty_cols = [c for h, c in col.items() if h.startswith("Quantity") and h != "Quantity Long Term"]
        out = []
        for r in rows[i + 1:]:
            sym = _cell(r[col["Symbol"]]) if col["Symbol"] < len(r) else ""
            if not sym:
                continue
            qty = sum(_num(r[c]) for c in qty_cols if c < len(r))
            out.append({"symbol": sym.upper(), "isin": _cell(r[col["ISIN"]]) if "ISIN" in col else "", "qty": qty,
                        "avg_price": _num(r[col["Average Price"]]) if "Average Price" in col else 0})
        return {"client_id": meta["client_id"], "as_of": meta["as_of"] or date.today().isoformat(), "rows": out}
    raise ImportError_(f"{name}: no holdings table found")


def fingerprint(account, t):
    return "|".join([account, t["exchange"], t["trade_id"], t["order_id"], t["symbol"], t["side"],
                     f"{t['qty']:g}", f"{t['price']:g}", t["trade_date"]])


def _client_owner(session, client_id):
    if not client_id:
        return None
    row = session.query(EquityTrade.account).filter(EquityTrade.client_id == client_id).first()
    return row[0] if row else None


def _audit(session, **kw):
    detail = kw.pop("detail", None)
    a = EquityAudit(detail=json.dumps(detail) if detail is not None else "", **kw)
    session.add(a)
    session.flush()
    return a


def import_files(session, account, files, canonical):
    """files: [(name, bytes)]. `canonical(raw_symbol, known)` maps a broker symbol to the stored one.
    Returns [{file, kind, summary}] and commits once at the end (all files or none)."""
    account = (account or "").strip().upper()
    if not account or len(account) > 12:
        raise ImportError_("Pick the demat account these files belong to")
    results = []
    # tradebooks first, so dividend symbols can be matched against the traded names
    typed = [(sniff(n, d), n, d) for n, d in files]
    order = {"tradebook": 0, "holdings": 1, "dividends": 2}
    for kind, name, data in sorted(typed, key=lambda x: order[x[0]]):
        session.flush()   # the session doesn't autoflush: make earlier files' rows visible to this file's queries
        if kind == "tradebook":
            results.append(_import_tradebook(session, account, name, data))
        elif kind == "holdings":
            results.append(_import_holdings(session, account, name, data))
        else:
            results.append(_import_dividends(session, account, name, data, canonical))
    session.commit()
    return results


def _check_client(session, account, client_id, name):
    owner = _client_owner(session, client_id)
    if owner and owner != account:
        raise ImportError_(f"{name} is for client {client_id}, which is already imported as account {owner}")


def _import_tradebook(session, account, name, data):
    tb = parse_tradebook(name, data)
    _check_client(session, account, tb["client_id"], name)
    have = {f for (f,) in session.query(EquityTrade.fingerprint).filter(EquityTrade.account == account)}
    audit = _audit(session, kind="tradebook", account=account, file_name=name,
                   period_from=(tb["period"] or ("", ""))[0], period_to=(tb["period"] or ("", ""))[1])
    added, dup = 0, 0
    for t in tb["trades"]:
        fp = fingerprint(account, t)
        if fp in have:
            dup += 1
            continue
        have.add(fp)
        session.add(EquityTrade(account=account, client_id=tb["client_id"], fingerprint=fp, import_id=audit.id, **t))
        added += 1
    audit.summary = f"{added} trades added, {dup} already present"
    audit.detail = json.dumps({"client_id": tb["client_id"], "added": added, "duplicates": dup, "rows": len(tb["trades"])})
    return {"file": name, "kind": "tradebook", "summary": audit.summary, "period": tb["period"]}


def _import_holdings(session, account, name, data):
    h = parse_holdings(name, data)
    _check_client(session, account, h["client_id"], name)
    removed = session.query(BrokerHolding).filter(BrokerHolding.account == account).delete(synchronize_session=False)
    audit = _audit(session, kind="holdings", account=account, file_name=name, period_to=h["as_of"])
    for r in h["rows"]:
        session.add(BrokerHolding(account=account, as_of=h["as_of"], import_id=audit.id, **r))
    audit.summary = f"{len(h['rows'])} holdings as of {h['as_of']} (replaced {removed} earlier lines)"
    audit.detail = json.dumps({"client_id": h["client_id"], "rows": h["rows"]})
    return {"file": name, "kind": "holdings", "summary": audit.summary, "period": (h["as_of"], h["as_of"])}


def _import_dividends(session, account, name, data, canonical):
    dv = parse_dividends(name, data)
    lo, hi = dv["period"]
    known = {s for (s,) in session.query(EquityTrade.symbol).filter(EquityTrade.account == account).distinct()}
    q = session.query(EquityDividend).filter(EquityDividend.account == account, EquityDividend.ex_date >= lo,
                                             EquityDividend.ex_date <= hi)
    before = {(d.symbol, d.ex_date, d.dps): d.amount for d in q.filter(EquityDividend.source == "zerodha")}
    yahoo_removed = [(d.symbol, d.ex_date, d.amount) for d in q.filter(EquityDividend.source == "yahoo")]
    q.delete(synchronize_session=False)
    audit = _audit(session, kind="dividends", account=account, file_name=name, period_from=lo, period_to=hi)
    seen, after = set(), {}
    for r in dv["rows"]:
        sym = canonical(r["raw_symbol"], known)
        k = (sym, r["ex_date"], r["dps"])
        if k in seen:   # Console repeats a row when the same payout appears twice; keep one
            continue
        seen.add(k)
        after[k] = r["amount"]
        session.add(EquityDividend(account=account, symbol=sym, ex_date=r["ex_date"], qty=r["qty"], dps=r["dps"],
                                   amount=r["amount"], raw_symbol=r["raw_symbol"], source="zerodha", import_id=audit.id))
    new = [list(k) for k in after if k not in before]
    changed = [list(k) + [before[k], after[k]] for k in after if k in before and abs(before[k] - after[k]) > 0.005]
    gone = [list(k) for k in before if k not in after]
    audit.summary = (f"{len(after)} dividends, ₹{sum(after.values()):,.2f} ({len(new)} new, {len(changed)} changed, "
                     f"{len(gone)} removed{f', {len(yahoo_removed)} fetched rows replaced' if yahoo_removed else ''})")
    audit.detail = json.dumps({"new": new, "changed": changed, "removed": gone, "yahoo_replaced": yahoo_removed})
    return {"file": name, "kind": "dividends", "summary": audit.summary, "period": dv["period"]}
