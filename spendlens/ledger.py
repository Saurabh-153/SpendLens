"""Transaction ledger: buys, sells, dividends and opening balances with dates.

The holdings table stays the current position. A ledger row can also update it ("apply"), or be a pure record
of something that already happened. Deleting a row never touches the holding.

kinds: BUY (cash out), SELL (cash in), DIVIDEND (cash in), OPENING (money already in the holding, with the date it went in).
Realised gain is measured against the holding's average cost (no lot tracking), which is exact for averaged SIP-style buying.
"""
from datetime import date

from accrual import _deposits, _iso
from db.base import row_dict
from db.models import Holding
from db.models.portfolio import LedgerTransaction
from portfolio import xirr

KINDS = ("BUY", "SELL", "DIVIDEND", "OPENING")
DIRECT = ("MF", "FD", "PF")


def rows(session):
    """Every ledger row as a dict, oldest first."""
    return [row_dict(t) for t in session.query(LedgerTransaction).order_by(LedgerTransaction.tx_date, LedgerTransaction.id).all()]


def fy_of(d):
    """Indian financial year label for an ISO date: 2026-04-01 .. 2027-03-31 -> FY2026-27."""
    y = int(d[:4]) + (1 if int(d[5:7]) >= 4 else 0)
    return f"FY{y - 1}-{str(y)[2:]}"


def add(session, d, h=None):
    """Insert a transaction; `h` is the holding as a dict (or None). Returns the new id. Raises ValueError for bad input."""
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
        row = session.get(Holding, h["id"])
        if priced:
            if kind == "BUY":
                nq = h["qty"] + qty
                row.qty, row.buy_price = nq, (h["qty"] * h["buy_price"] + amount) / nq
                row.cmp = h["cmp"] if (h["cmp"] or 0) > 0 else price
            else:
                if qty > h["qty"] + 1e-9:
                    raise ValueError(f"You only hold {h['qty']:g}")
                row.qty = h["qty"] - qty
        else:
            value = h["qty"] * h["cmp"]
            if kind == "BUY":
                units = h["units"] + amount / h["nav"] if (h["units"] or 0) > 0 and (h["nav"] or 0) > 0 else h["units"]
                row.qty, row.buy_price = 1, h["qty"] * h["buy_price"] + amount
                row.cmp, row.units = (units * h["nav"]) if units and h["nav"] else value + amount, units or 0
            else:
                if amount > value + 0.5:
                    raise ValueError("Withdrawal is more than the holding is worth")
                frac = amount / value if value else 0
                row.qty, row.buy_price = 1, h["qty"] * h["buy_price"] * (1 - frac)
                row.cmp, row.units = value * (1 - frac), (h["units"] or 0) * (1 - frac)
    t = LedgerTransaction(holding_id=h["id"] if h else None, name=(h["name"] if h else d.get("name", "")).strip(), tx_date=d["tx_date"],
                          kind=kind, qty=qty, price=price, amount=round(amount, 2), fees=fees, realized=round(realized, 2),
                          note=d.get("note", ""), source=d.get("source", "manual"), applied=applied)
    session.add(t)
    session.commit()
    return t.id


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


def summary(session, held, today=None):
    """Per-financial-year totals and XIRR (portfolio and per holding) from the ledger."""
    today = today or date.today()
    txs_all = rows(session)
    fys = {}
    for r in txs_all:
        f = fys.setdefault(fy_of(r["tx_date"]), {"fy": fy_of(r["tx_date"]), "dividends": 0.0, "realized": 0.0, "bought": 0.0, "sold": 0.0})
        if r["kind"] == "DIVIDEND":
            f["dividends"] += r["amount"]
        elif r["kind"] == "SELL":
            f["sold"] += r["amount"]; f["realized"] += r["realized"]
        elif r["kind"] == "BUY":
            f["bought"] += r["amount"]
    by_h = {}
    for r in txs_all:
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
