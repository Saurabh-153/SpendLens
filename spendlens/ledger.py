"""Transaction ledger: buys, sells, dividends and opening balances with dates.

The holdings table stays the current position. A ledger row can also update it ("apply"), or be a pure record
of something that already happened. Deleting a row never touches the holding.

kinds: BUY (cash out), SELL (cash in), DIVIDEND (cash in), OPENING (money already in the holding, with the date it went in).
Realised gain is measured against the holding's average cost (no lot tracking), which is exact for averaged SIP-style buying.
"""
from datetime import date

from accrual import _deposits, _iso
from portfolio import xirr

KINDS = ("BUY", "SELL", "DIVIDEND", "OPENING")
DIRECT = ("MF", "FD", "PF")


def ensure(db):
    # user_id is baked in here (not left for database.py's _m003_user_id_columns to ALTER in)
    # because this table is created lazily, on first use - _add_column skips tables that don't
    # exist yet, so on a genuinely fresh database that migration would otherwise permanently
    # no-op before this CREATE ever runs. Same reasoning as portfolio_goals in portfolio.py.
    db.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, holding_id INTEGER, name TEXT DEFAULT '', tx_date TEXT NOT NULL, kind TEXT NOT NULL,
        qty REAL DEFAULT 0, price REAL DEFAULT 0, amount REAL DEFAULT 0, fees REAL DEFAULT 0, realized REAL DEFAULT 0,
        note TEXT DEFAULT '', source TEXT DEFAULT 'manual', applied INTEGER DEFAULT 0, user_id INTEGER DEFAULT 1)""")
    db.commit()


def fy_of(d):
    """Indian financial year label for an ISO date: 2026-04-01 .. 2027-03-31 -> FY2026-27."""
    y = int(d[:4]) + (1 if int(d[5:7]) >= 4 else 0)
    return f"FY{y - 1}-{str(y)[2:]}"


def add(db, d, h=None):
    """Insert a transaction; `h` is the holding row (or None). Returns the new id. Raises ValueError for bad input."""
    kind = d["kind"].upper()
    if kind not in KINDS:
        raise ValueError("Unknown transaction type")
    if _iso(d["tx_date"]) is None:
        raise ValueError("Enter a valid date")
    if kind != "DIVIDEND" and not h:
        raise ValueError("Pick a holding")
    qty, price, fees, amount = float(d.get("qty") or 0), float(d.get("price") or 0), float(d.get("fees") or 0), float(d.get("amount") or 0)
    priced = bool(h) and h["asset_type"] not in DIRECT
    realized, applied = 0.0, 0

    if kind in ("BUY", "SELL") and priced:
        if qty <= 0 or price <= 0:
            raise ValueError("Enter quantity and price")
        amount = qty * price + fees if kind == "BUY" else qty * price - fees
    elif kind == "DIVIDEND" and amount <= 0:
        amount = qty * price
    if amount <= 0 and kind != "OPENING":
        raise ValueError("Enter an amount")
    if kind == "OPENING" and amount <= 0:
        amount = h["qty"] * h["buy_price"]

    if kind == "SELL":
        if priced:
            realized = amount - qty * h["buy_price"]
        elif h:
            value = h["qty"] * h["cmp"]
            frac = min(amount / value, 1) if value else 0
            realized = amount - h["qty"] * h["buy_price"] * frac
    if d.get("apply") and kind in ("BUY", "SELL") and h:
        applied = 1
        if priced:
            if kind == "BUY":
                nq = h["qty"] + qty
                db.execute("UPDATE holdings SET qty=?, buy_price=?, cmp=CASE WHEN cmp>0 THEN cmp ELSE ? END WHERE id=?",
                           (nq, (h["qty"] * h["buy_price"] + amount) / nq, price, h["id"]))
            else:
                if qty > h["qty"] + 1e-9:
                    raise ValueError(f"You only hold {h['qty']:g}")
                db.execute("UPDATE holdings SET qty=? WHERE id=?", (h["qty"] - qty, h["id"]))
        else:
            value = h["qty"] * h["cmp"]
            if kind == "BUY":
                units = h["units"] + amount / h["nav"] if (h["units"] or 0) > 0 and (h["nav"] or 0) > 0 else h["units"]
                db.execute("UPDATE holdings SET qty=1, buy_price=?, cmp=?, units=? WHERE id=?",
                           (h["qty"] * h["buy_price"] + amount, (units * h["nav"]) if units and h["nav"] else value + amount, units or 0, h["id"]))
            else:
                if amount > value + 0.5:
                    raise ValueError("Withdrawal is more than the holding is worth")
                frac = amount / value if value else 0
                db.execute("UPDATE holdings SET qty=1, buy_price=?, cmp=?, units=? WHERE id=?",
                           (h["qty"] * h["buy_price"] * (1 - frac), value * (1 - frac), (h["units"] or 0) * (1 - frac), h["id"]))
    cur = db.execute("""INSERT INTO transactions (holding_id, name, tx_date, kind, qty, price, amount, fees, realized, note, source, applied)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (h["id"] if h else None, (h["name"] if h else d.get("name", "")).strip(), d["tx_date"], kind, qty, price, round(amount, 2),
                      fees, round(realized, 2), d.get("note", ""), d.get("source", "manual"), applied))
    db.commit()
    return cur.lastrowid


def _virtual_flows(h, today):
    """Dated outflows for auto-valued FD / RD holdings that have no ledger rows (opening date and deposits are known)."""
    start = _iso(h.get("start_date"))
    if not (h.get("auto") and start):
        return []
    if h.get("rd") and (h.get("sip_amount") or 0) > 0:
        end = _iso(h.get("maturity"))
        last = min(today, end) if end else today
        return [(d, -h["sip_amount"]) for d in _deposits(start, h.get("sip_day") or 0, last, bool(end and end <= today))]
    return [(start, -h["invested"])]


def summary(db, held, today=None):
    """Per-financial-year totals and XIRR (portfolio and per holding) from the ledger."""
    today = today or date.today()
    ensure(db)
    rows = [dict(r) for r in db.execute("SELECT * FROM transactions ORDER BY tx_date, id")]
    fys = {}
    for r in rows:
        f = fys.setdefault(fy_of(r["tx_date"]), {"fy": fy_of(r["tx_date"]), "dividends": 0.0, "realized": 0.0, "bought": 0.0, "sold": 0.0})
        if r["kind"] == "DIVIDEND":
            f["dividends"] += r["amount"]
        elif r["kind"] == "SELL":
            f["sold"] += r["amount"]; f["realized"] += r["realized"]
        elif r["kind"] == "BUY":
            f["bought"] += r["amount"]
    by_h = {}
    for r in rows:
        if r["holding_id"]:
            by_h.setdefault(r["holding_id"], []).append(r)
    out, all_flows, covered_val, total_val = [], [], 0.0, sum(h["present"] for h in held)
    for h in held:
        txs = by_h.get(h["id"], [])
        flows = []
        has_start = any(t["kind"] in ("OPENING", "BUY") for t in txs)
        for t in txs:
            d = _iso(t["tx_date"])
            if t["kind"] in ("OPENING", "BUY"):
                flows.append((d, -t["amount"]))
            elif t["kind"] in ("SELL", "DIVIDEND"):
                flows.append((d, t["amount"]))
        if not has_start:
            v = _virtual_flows(h, today)
            if v:
                flows += v; has_start = True
        divs = sum(t["amount"] for t in txs if t["kind"] == "DIVIDEND")
        item = {"id": h["id"], "name": h["name"], "grp": h.get("grp") or "Others", "type": h["asset_type"], "invested": h["invested"], "present": h["present"],
                "dividends": round(divs, 2), "since": None, "xirr": None, "covered": has_start}
        if has_start and flows:
            flows.sort()
            item["since"] = flows[0][0].isoformat()
            fl = flows + ([(today, h["present"])] if h["present"] > 0 else [])
            if (fl[-1][0] - fl[0][0]).days >= 30:
                r = xirr(fl)
                item["xirr"] = None if r is None else round(r * 100, 2)
            all_flows += fl
            covered_val += h["present"]
        out.append(item)
    portfolio = None
    if all_flows:
        merged = {}
        for d, a in all_flows:
            merged[d] = merged.get(d, 0) + a
        fl = sorted(merged.items())
        if len(fl) > 1 and (fl[-1][0] - fl[0][0]).days >= 30:
            r = xirr(fl)
            portfolio = None if r is None else round(r * 100, 2)
    cur = fy_of(today.isoformat())
    return {"fy": sorted(fys.values(), key=lambda x: x["fy"], reverse=True), "current_fy": cur,
            "xirr": {"portfolio": portfolio, "covered_pct": round(covered_val / total_val * 100, 1) if total_val else 0, "holdings": out},
            "dividends_total": round(sum(f["dividends"] for f in fys.values()), 2),
            "realized_total": round(sum(f["realized"] for f in fys.values()), 2)}
