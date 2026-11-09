"""Dated money flows per holding (the `transactions` table), for the Holdings KPI's XIRR.

SIPs write their instalments here (sip.py); older manually entered BUY / SELL / DIVIDEND / OPENING rows are kept.
The manual-entry Ledger screen was replaced by the stock ledger (equity.py), which works from broker tradebooks.
"""
from datetime import date

from accrual import _deposits, _iso
from db.base import row_dict
from db.models.portfolio import LedgerTransaction
from portfolio import xirr



def rows(session):
    """Every ledger row as a dict, oldest first."""
    return [row_dict(t) for t in session.query(LedgerTransaction).order_by(LedgerTransaction.tx_date, LedgerTransaction.id).all()]


def fy_of(d):
    """Indian financial year label for an ISO date: 2026-04-01 .. 2027-03-31 -> FY2026-27."""
    y = int(d[:4]) + (1 if int(d[5:7]) >= 4 else 0)
    return f"FY{y - 1}-{str(y)[2:]}"


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
