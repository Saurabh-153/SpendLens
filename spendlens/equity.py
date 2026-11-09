"""The stock ledger: replays every imported trade and corporate action per demat account into FIFO lots, then derives
positions, realised gains, dividends by quarter and year, XIRR per stock and for the portfolio, and the reconciliation
that proves the replay right: the share count on every statement ex-date and on the broker's holdings statement.

Ordering within a day: share-count actions (split, bonus, merger, demerger) apply at the start of their ex-date, then
allotments and transfers in, then trades, then buybacks and transfers out. A dividend belongs to the shares held at the
end of the day before its ex-date.

XIRR cash flows: buys out, sells / buybacks / dividends in, today's value in at the end. Demergers and mergers move
cost between symbols as an equal and opposite flow on the same day, so the portfolio XIRR is exact whatever cost split
is used. A stock holding shares of unknown cost (an allotment or transfer with no price) is left out of XIRR.
"""
import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta

from db.models import BrokerHolding, EquityAudit, EquityDividend, EquityEvent, EquitySecurity, EquityTrade
from portfolio import xirr

KINDS = ("SPLIT", "BONUS", "BUYBACK", "TRANSFER_OUT", "IPO", "TRANSFER_IN", "ADJUST", "DEMERGER", "MERGER", "RENAME")
_ORDER = {"SPLIT": 0, "BONUS": 0, "MERGER": 0, "DEMERGER": 0, "RENAME": 0, "IPO": 1, "TRANSFER_IN": 1, "ADJUST": 1,
          "TRADE": 2, "BUYBACK": 3, "TRANSFER_OUT": 3}

# Symbols the exchange renamed: history under the old name continues under the new one.
ALIASES = {"DEEPAKNI": "DEEPAKNTR", "EUREKAFORBE": "EUREKAFORB", "AMARAJABAT": "ARE&M", "MCDOWELL-N": "UNITDSPR",
           "PVR": "PVRINOX", "MOTHERSUMI": "MOTHERSON"}

# Share-count actions Yahoo's split history misses. Yahoo lists bonuses as splits for most stocks, but not these.
BUILTIN_EVENTS = [
    {"symbol": "BAJFINANCE", "ex_date": "2025-06-16", "kind": "BONUS", "ratio_new": 4, "ratio_old": 1,
     "note": "4:1 bonus, same record date as the 2:1 split (Yahoo lists only the split)"},
    {"symbol": "AARTIIND", "ex_date": "2022-10-19", "kind": "DEMERGER", "ratio_new": 1, "ratio_old": 4,
     "target_symbol": "AARTIPHARM", "cost_pct": 24.42,
     "note": "Aarti Pharmalabs demerged, record date 2022-10-20; cost split 24.42% / 75.58% per the company's note"},
]

EPS = 1e-6


def fy_of(d):
    y = int(d[:4]) + (1 if int(d[5:7]) >= 4 else 0)
    return f"FY{y - 1}-{str(y)[2:]}"


def fq_of(d):
    """Indian financial-year quarter: Apr-Jun is Q1 ... Jan-Mar is Q4."""
    return f"{fy_of(d)} Q{(int(d[5:7]) - 4) % 12 // 3 + 1}"


def factor(e):
    """Shares after per share before, for a SPLIT (new:old) or a BONUS (new free per old held)."""
    new, old = float(e["ratio_new"] or 0), float(e["ratio_old"] or 0)
    if new <= 0 or old <= 0:
        return 1.0
    return new / old if e["kind"] == "SPLIT" else (new + old) / old


def _ev_dict(e):
    return {k: getattr(e, k) for k in ("id", "account", "symbol", "ex_date", "kind", "ratio_new", "ratio_old", "qty", "price",
                                       "target_symbol", "cost_pct", "note", "source")}


def all_events(session):
    out = [_ev_dict(e) for e in session.query(EquityEvent).order_by(EquityEvent.ex_date, EquityEvent.id)]
    for i, b in enumerate(BUILTIN_EVENTS):
        if not any(e["kind"] == b["kind"] and e["symbol"] == b["symbol"] and e["ex_date"] == b["ex_date"] for e in out):
            out.append({"id": -(i + 1), "account": "", "qty": 0, "price": None, "target_symbol": "", "cost_pct": 0,
                        "source": "builtin", **b})
    return out


def make_canonical(events):
    renames = dict(ALIASES)
    for e in events:
        if e["kind"] == "RENAME" and e["target_symbol"]:
            renames[e["symbol"].upper()] = e["target_symbol"].upper()

    def canon(sym):
        s = (sym or "").upper().strip()
        for _ in range(5):   # follow chains A -> B -> C
            if s not in renames:
                break
            s = renames[s]
        return s
    return canon


def dividend_symbol(raw, known, canon=lambda s: s):
    """Console prints dividend symbols with suffixes ("BAJFINANCE6", "INFY#"): strip them back to a traded symbol."""
    s = raw.upper().strip()
    for cand in (s, re.sub(r"[#*]+$", "", s), re.sub(r"[#*\d]+$", "", s)):
        if cand and (cand in known or canon(cand) in known):
            return canon(cand)
    t = re.sub(r"[#*\d]+$", "", s)
    return canon(t or s)


class Lot:
    __slots__ = ("qty", "cost", "date")

    def __init__(self, qty, cost, d):
        self.qty, self.cost, self.date = qty, cost, d   # cost: per share, or None when unknown


class Position:
    def __init__(self, account, symbol):
        self.account, self.symbol = account, symbol
        self.lots = []
        self.flows = []            # (date iso, amount) excluding dividends
        self.realized = 0.0
        self.unknown_cost = False  # some shares ever held had no cost
        self.timeline = []         # (date, kind, qty, price, amount, qty_after, note)
        self.qty_steps = []        # (date, qty after) in replay order
        self.first = None
        self.last_zero = None

    @property
    def qty(self):
        return sum(lot.qty for lot in self.lots)

    def cost_basis(self):
        return sum(lot.qty * lot.cost for lot in self.lots if lot.cost is not None)

    def qty_before(self, d):
        """Shares held at the end of the day before `d`."""
        q = 0.0
        for dd, after in self.qty_steps:
            if dd >= d:
                break
            q = after
        return q

    def qty_through(self, d):
        q = 0.0
        for dd, after in self.qty_steps:
            if dd > d:
                break
            q = after
        return q

    def step(self, d, kind, qty, price=None, amount=0.0, note=""):
        after = round(self.qty, 6)
        self.qty_steps.append((d, after))
        self.timeline.append({"date": d, "account": self.account, "kind": kind, "qty": round(qty, 6),
                              "price": price, "amount": round(amount, 2), "qty_after": after, "note": note})
        if self.first is None and after > EPS:
            self.first = d
        if after <= EPS and kind not in ("SPLIT", "BONUS"):
            self.last_zero = d

    def add(self, qty, cost, d):
        self.lots.append(Lot(qty, cost, d))
        if cost is None:
            self.unknown_cost = True

    def take(self, qty):
        """Remove qty FIFO. Returns (cost of known lots taken, unknown-cost qty taken, qty missing)."""
        cost, unknown, need = 0.0, 0.0, qty
        while need > EPS and self.lots:
            lot = self.lots[0]
            q = min(lot.qty, need)
            if lot.cost is None and q > EPS:
                unknown += q
            else:
                cost += q * lot.cost
            lot.qty -= q
            need -= q
            if lot.qty <= EPS:
                self.lots.pop(0)
        return cost, unknown, max(need, 0.0)

    def scale(self, f):
        before = self.qty
        for lot in self.lots:
            lot.qty *= f
            if lot.cost is not None:
                lot.cost /= f
        target = math.floor(before * f + 1e-6)   # fractional entitlements are paid out in cash, not shares
        extra = self.qty - target
        if self.lots and extra > EPS:
            self.lots[-1].qty -= extra


def replay(session, accounts=None):
    """{(account, symbol): Position}, plus the replay's own problems (sold more than held)."""
    events = all_events(session)
    canon = make_canonical(events)
    tq = session.query(EquityTrade)
    if accounts:
        tq = tq.filter(EquityTrade.account.in_(accounts))
    trades = tq.order_by(EquityTrade.trade_date, EquityTrade.executed_at, EquityTrade.id).all()
    accts = sorted({t.account for t in trades} | set(accounts or []))
    pos, problems = {}, []

    def P(a, s):
        return pos.setdefault((a, s), Position(a, s))

    for acct in accts:
        items = []
        for t in trades:
            if t.account == acct:
                items.append((t.trade_date, _ORDER["TRADE"], t.id, "TRADE", t))
        for e in events:
            if e["kind"] != "RENAME" and e["account"] in ("", acct):
                items.append((e["ex_date"], _ORDER.get(e["kind"], 1), e["id"], e["kind"], e))
        items.sort(key=lambda x: (x[0], x[1], x[2]))
        for d, _, _, kind, it in items:
            if kind == "TRADE":
                p = P(acct, canon(it.symbol))
                amt = it.qty * it.price
                if it.side == "BUY":
                    p.add(it.qty, it.price, d)
                    p.flows.append((d, -amt))
                else:
                    cost, unknown, missing = p.take(it.qty)
                    p.flows.append((d, amt))
                    known_qty = it.qty - unknown - missing
                    p.realized += known_qty * it.price - cost
                    if unknown > EPS or missing > EPS:
                        p.unknown_cost = True
                    if missing > EPS:
                        problems.append({"level": "error", "kind": "oversold", "account": acct, "symbol": p.symbol,
                                         "date": d, "delta": round(missing, 4),
                                         "message": f"Sold {it.qty:g} on {d} but the history holds only {it.qty - missing:g}",
                                         "hint": "Shares are missing before this sale: a bonus, split, IPO allotment or transfer in."})
                p.step(d, it.side, it.qty, it.price, amt)
                continue
            e = it
            sym = canon(e["symbol"])
            if (acct, sym) not in pos and kind not in ("IPO", "TRANSFER_IN", "ADJUST"):
                continue   # a market-wide action for a stock this account never held
            p = P(acct, sym)
            note = e.get("note") or ""
            if kind in ("SPLIT", "BONUS"):
                if p.qty <= EPS:
                    continue
                f = factor(e)
                q0 = p.qty
                p.scale(f)
                p.step(d, kind, p.qty - q0, note=f"{e['ratio_new']:g}:{e['ratio_old']:g} {note}".strip())
            elif kind in ("IPO", "TRANSFER_IN") or (kind == "ADJUST" and (e["qty"] or 0) > 0):
                q, price = float(e["qty"] or 0), e["price"]
                if q <= 0:
                    continue
                p.add(q, price, d)
                if price is not None:
                    p.flows.append((d, -q * price))
                p.step(d, kind, q, price, (q * price) if price is not None else 0, note)
            elif kind in ("BUYBACK", "TRANSFER_OUT") or (kind == "ADJUST" and (e["qty"] or 0) < 0):
                q, price = abs(float(e["qty"] or 0)), e["price"]
                if q <= 0:
                    continue
                cost, unknown, missing = p.take(q)
                if price is not None:
                    p.flows.append((d, q * price))
                    p.realized += (q - unknown - missing) * price - cost
                elif cost:
                    # leaves with no price: treat as leaving at cost, so XIRR is not distorted
                    p.flows.append((d, cost))
                if missing > EPS:
                    problems.append({"level": "error", "kind": "oversold", "account": acct, "symbol": sym, "date": d,
                                     "delta": round(missing, 4), "message": f"{kind.title()} of {q:g} on {d} exceeds the {q - missing:g} held",
                                     "hint": "Check the quantity of this event."})
                p.step(d, kind, -q, price, (q * price) if price is not None else 0, note)
            elif kind in ("DEMERGER", "MERGER"):
                held = p.qty
                tgt = canon(e["target_symbol"])
                if held <= EPS or not tgt:
                    continue
                c = P(acct, tgt)
                new_qty = float(e["qty"] or 0) or math.floor(held * float(e["ratio_new"] or 0) / float(e["ratio_old"] or 1) + 1e-6)
                if kind == "DEMERGER":
                    pct = float(e["cost_pct"] or 0) / 100
                    moved = 0.0
                    for lot in p.lots:
                        if lot.cost is not None:
                            moved += lot.qty * lot.cost * pct
                            lot.cost *= (1 - pct)
                    if new_qty > 0:
                        c.add(new_qty, (moved / new_qty) if pct > 0 else None, d)
                    if p.unknown_cost:
                        c.unknown_cost = True
                    if moved:
                        p.flows.append((d, moved))
                        c.flows.append((d, -moved))
                    p.step(d, kind, 0, note=f"{new_qty:g} {tgt} received {note}".strip())
                    c.step(d, kind, new_qty, note=f"demerged from {sym}" + ("" if pct else ": cost split not set"))
                else:
                    cost, unknown, _ = p.take(held)
                    c.add(new_qty, cost / new_qty if new_qty and not unknown else None, d)
                    if unknown:
                        c.unknown_cost = True
                    if cost:
                        p.flows.append((d, cost))
                        c.flows.append((d, -cost))
                    p.step(d, kind, -held, note=f"became {new_qty:g} {tgt}")
                    c.step(d, kind, new_qty, note=f"from {held:g} {sym}")
    return pos, problems, canon


def _dividends(session, accounts=None):
    q = session.query(EquityDividend)
    if accounts:
        q = q.filter(EquityDividend.account.in_(accounts))
    return q.order_by(EquityDividend.ex_date).all()


def _prices(session):
    return {s.symbol: s for s in session.query(EquitySecurity)}


SALE_KINDS = ("SELL", "BUYBACK")
ENTRY_KINDS = ("BUY", "IPO", "TRANSFER_IN", "ADJUST", "DEMERGER", "MERGER")


def sales(ps):
    """All-time and closing sales of one stock across its accounts.

    sold_qty / sale_value: every sale and priced buyback, as traded. The exit is the run of sales after the last
    time shares came in (a buy, allotment, transfer or demerger): exit_qty, exit_price (quantity-weighted average)
    and exit_value. Only meaningful once the stock is exited."""
    rows = sorted((t for p in ps for t in p.timeline), key=lambda t: (t["date"], t["account"]))
    sold = [(abs(t["qty"]), t["price"]) for t in rows if t["kind"] in SALE_KINDS and t["price"] is not None]
    last_in = max((i for i, t in enumerate(rows) if t["kind"] in ENTRY_KINDS and t["qty"] > 0), default=-1)
    exit_ = [(abs(t["qty"]), t["price"]) for t in rows[last_in + 1:] if t["kind"] in SALE_KINDS and t["price"] is not None]
    eq_, ev = sum(q for q, _ in exit_), sum(q * pr for q, pr in exit_)
    return {"sold_qty": round(sum(q for q, _ in sold), 4), "sale_value": round(sum(q * pr for q, pr in sold), 2),
            "exit_qty": round(eq_, 4) if eq_ else None, "exit_price": round(ev / eq_, 2) if eq_ else None,
            "exit_value": round(ev, 2) if eq_ else None}


def _xirr_pct(flows):
    if len(flows) < 2:
        return None
    flows = sorted(flows)
    if (date.fromisoformat(flows[-1][0]) - date.fromisoformat(flows[0][0])).days < 30:
        return None
    merged = defaultdict(float)
    for d, a in flows:
        merged[d] += a
    r = xirr([(date.fromisoformat(d), a) for d, a in sorted(merged.items())])
    return None if r is None else round(r * 100, 2)


def account_list(session):
    return sorted({a for (a,) in session.query(EquityTrade.account).distinct()} |
                  {a for (a,) in session.query(EquityDividend.account).distinct()})


def coverage(session):
    """Per account: the last day the broker's dividend statements cover, and the last trade."""
    out = {}
    for a in account_list(session):
        stmt = [x.period_to for x in session.query(EquityAudit).filter(EquityAudit.kind == "dividends", EquityAudit.account == a)]
        last_trade = session.query(EquityTrade.trade_date).filter(EquityTrade.account == a).order_by(EquityTrade.trade_date.desc()).first()
        out[a] = {"statement_to": max(stmt) if stmt else None, "last_trade": last_trade[0] if last_trade else None}
    return out


def summary(session, account=None, today=None):
    today = today or date.today()
    accounts = [account] if account and account != "ALL" else None
    pos, problems, canon = replay(session, accounts)
    divs = _dividends(session, accounts)
    px = _prices(session)

    by_sym = defaultdict(list)
    for (a, s), p in pos.items():
        by_sym[s].append(p)
    div_by_sym = defaultdict(list)
    for d in divs:
        div_by_sym[d.symbol].append(d)

    market = defaultdict(list)   # market-wide splits / bonuses per symbol, to put an exit price on today's basis
    for e in all_events(session):
        if e["kind"] in ("SPLIT", "BONUS") and not e["account"]:
            market[canon(e["symbol"])].append(e)
    stocks, all_flows, all_flows_ex, covered_value, total_value = [], [], [], 0.0, 0.0
    for sym in sorted(set(by_sym) | set(div_by_sym)):
        ps = by_sym.get(sym, [])
        qty = sum(p.qty for p in ps)
        invested = sum(p.cost_basis() for p in ps)
        sec = px.get(sym)
        price = sec.last_price if sec and sec.last_price else None
        value = qty * price if (price and qty > EPS) else (0.0 if qty <= EPS else None)
        dv = div_by_sym.get(sym, [])
        dsum = sum(d.amount for d in dv)
        flows = [f for p in ps for f in p.flows]
        dflows = [(d.ex_date, d.amount) for d in dv]
        unknown = any(p.unknown_cost for p in ps)
        note, x, x_ex = None, None, None
        end = [(today.isoformat(), value)] if (value and qty > EPS) else []
        if unknown:
            note = "Some shares have no cost: add the price of the allotment / transfer"
        elif qty > EPS and value is None:
            note = "No current price yet: run Refresh"
        elif flows:
            x = _xirr_pct(flows + dflows + end)
            x_ex = _xirr_pct(flows + end)
            all_flows += flows + dflows + end
            all_flows_ex += flows + end
            covered_value += value or 0
        if value:
            total_value += value
        held = qty > EPS
        sold = sales(ps)
        exit_date = None if held else max((p.last_zero for p in ps if p.last_zero), default=None)
        since = {"split_factor_since_exit": None, "exit_price_adj": None, "change_since_exit_pct": None, "exit_value_now": None}
        if held:
            sold.update(exit_qty=None, exit_price=None, exit_value=None)
        elif sold["exit_price"] and exit_date:
            f = 1.0
            for e in market.get(sym, []):
                if e["ex_date"] > exit_date:
                    f *= factor(e)
            adj = sold["exit_price"] / f
            since = {"split_factor_since_exit": round(f, 6), "exit_price_adj": round(adj, 2),
                     "change_since_exit_pct": round((price - adj) / adj * 100, 1) if price else None,
                     "exit_value_now": round(sold["exit_qty"] * f * price, 2) if price else None}
        stocks.append({
            "symbol": sym, "name": (sec.name if sec else "") or sym, "status": "held" if held else "exited",
            "qty": round(qty, 4), "invested": round(invested, 2), "avg_cost": round(invested / qty, 2) if held and invested else None,
            "price": price, "price_date": sec.price_date if sec else "", "value": round(value, 2) if value is not None else None,
            "unrealized": round(value - invested, 2) if (value is not None and held and not unknown) else None,
            "realized": round(sum(p.realized for p in ps), 2), "dividends": round(dsum, 2),
            "xirr": x, "xirr_ex_div": x_ex, "xirr_note": note,
            "first_date": min((p.first for p in ps if p.first), default=None),
            "exit_date": exit_date,
            "accounts": {p.account: round(p.qty, 4) for p in ps if p.qty > EPS},
            **sold, **since,
        })

    cur_fy = fy_of(today.isoformat())
    quarters = sorted({fq_of(d.ex_date) for d in divs})
    years = sorted({fy_of(d.ex_date) for d in divs})
    status = {s["symbol"]: s["status"] for s in stocks}
    drows = {}
    for d in divs:
        r = drows.setdefault(d.symbol, {"symbol": d.symbol, "status": status.get(d.symbol, "exited"), "by_quarter": defaultdict(float),
                                        "by_year": defaultdict(float), "total": 0.0, "sources": set()})
        r["by_quarter"][fq_of(d.ex_date)] += d.amount
        r["by_year"][fy_of(d.ex_date)] += d.amount
        r["total"] += d.amount
        r["sources"].add(d.source)
    rows = []
    for r in sorted(drows.values(), key=lambda r: -r["total"]):
        rows.append({"symbol": r["symbol"], "status": r["status"], "total": round(r["total"], 2), "sources": sorted(r["sources"]),
                     "by_quarter": {k: round(v, 2) for k, v in r["by_quarter"].items()},
                     "by_year": {k: round(v, 2) for k, v in r["by_year"].items()}})
    tq, ty = defaultdict(float), defaultdict(float)
    for d in divs:
        tq[fq_of(d.ex_date)] += d.amount
        ty[fy_of(d.ex_date)] += d.amount

    held = [s for s in stocks if s["status"] == "held"]
    issues = reconcile(session, accounts, pos, problems, canon, divs)
    return {
        "accounts": account_list(session), "account": account or "ALL", "as_of": today.isoformat(), "current_fy": cur_fy,
        "kpis": {
            "value": round(sum(s["value"] or 0 for s in held), 2),
            "invested": round(sum(s["invested"] for s in held), 2),
            "unrealized": round(sum(s["unrealized"] or 0 for s in held), 2),
            "realized": round(sum(s["realized"] for s in stocks), 2),
            "dividends_total": round(sum(d.amount for d in divs), 2),
            "dividends_fy": round(ty.get(cur_fy, 0), 2),
            "xirr": _xirr_pct(all_flows), "xirr_ex_div": _xirr_pct(all_flows_ex),
            "xirr_coverage_pct": round(covered_value / total_value * 100, 1) if total_value else None,
            "held_count": len(held), "exited_count": len(stocks) - len(held),
        },
        "stocks": stocks,
        "dividends": {"quarters": quarters, "years": years, "rows": rows,
                      "totals_by_quarter": {k: round(v, 2) for k, v in tq.items()},
                      "totals_by_year": {k: round(v, 2) for k, v in ty.items()}},
        "coverage": coverage(session),
        "issue_counts": {lvl: sum(1 for i in issues if i["level"] == lvl) for lvl in ("error", "warning", "info")},
    }


RATIOS = {2: "1:1 bonus or 2:1 split", 3: "2:1 bonus or 3:1 split", 5: "5:1 split or 4:1 bonus", 10: "10:1 split",
          1.5: "1:2 bonus or 3:2 split", 4 / 3: "1:3 bonus", 1.25: "1:4 bonus or 5:4 split", 1.2: "1:5 bonus or 6:5 split"}


def _hint(expected, got, any_trades):
    if got <= EPS and not any_trades:
        return "No trades for this stock in this account: the shares came from an IPO allotment, demerger, merger or transfer in."
    if got > EPS:
        r = expected / got
        for k, v in RATIOS.items():
            if abs(r - k) < 0.02:
                return f"Ratio {r:.2f}: looks like a missing {v}."
    d = expected - got
    if d > 0:
        return f"{d:g} more shares than the trades explain: a bonus, IPO allotment or transfer in."
    return f"{-d:g} fewer shares than the trades explain: a buyback tender, transfer out, or an action on the wrong date."


def reconcile(session, accounts, pos, problems, canon, divs):
    """Every reason to doubt the replay, most serious first."""
    issues = list(problems)
    # 1. statement share counts on each ex-date
    groups = {}
    for d in divs:
        if d.source != "zerodha":
            continue
        p = pos.get((d.account, d.symbol))
        got = p.qty_before(d.ex_date) if p else 0.0
        if abs(got - d.qty) <= 0.001:
            continue
        key = (d.account, d.symbol, round(d.qty - got, 4))
        g = groups.setdefault(key, {"dates": [], "expected": d.qty, "got": got})
        g["dates"].append(d.ex_date)
    for (a, s, delta), g in groups.items():
        p = pos.get((a, s))
        any_trades = bool(p and any(t["kind"] in ("BUY", "SELL") for t in p.timeline))
        ds = g["dates"]
        issues.append({"level": "error", "kind": "qty_mismatch", "account": a, "symbol": s, "date": ds[0], "date_to": ds[-1],
                       "count": len(ds), "expected": g["expected"], "replay": round(g["got"], 4), "delta": delta,
                       "message": f"Dividend statement shows {g['expected']:g} shares on {ds[0]}"
                                  f"{f' (and {len(ds) - 1} later ex-dates)' if len(ds) > 1 else ''}; trades give {g['got']:g}",
                       "hint": _hint(g["expected"], g["got"], any_trades)})
    # 2. the broker's holdings statement
    hq = session.query(BrokerHolding)
    if accounts:
        hq = hq.filter(BrokerHolding.account.in_(accounts))
    stmt = defaultdict(list)
    for h in hq:
        stmt[h.account].append(h)
    for a in (accounts or account_list(session)):
        if a not in stmt:
            issues.append({"level": "info", "kind": "no_statement", "account": a, "symbol": "", "date": "",
                           "message": f"No holdings statement for {a} yet",
                           "hint": "Upload Console › Portfolio › Holdings (xlsx) to confirm every share count."})
            continue
        as_of = stmt[a][0].as_of
        want = defaultdict(float)
        for h in stmt[a]:
            want[canon(h.symbol)] += h.qty
        have = {s: p.qty_through(as_of) for (acct, s), p in pos.items() if acct == a}
        for s in sorted(set(want) | {s for s, q in have.items() if q > EPS}):
            w, g = want.get(s, 0.0), have.get(s, 0.0)
            if abs(w - g) > 0.001:
                p = pos.get((a, s))
                issues.append({"level": "error", "kind": "holding_mismatch", "account": a, "symbol": s, "date": as_of,
                               "expected": w, "replay": round(g, 4), "delta": round(w - g, 4),
                               "message": f"Holdings statement ({as_of}) shows {w:g}; trades give {g:g}",
                               "hint": _hint(w, g, bool(p and p.timeline))})
    # 3. what keeps XIRR from being complete
    px = _prices(session)
    for (a, s), p in sorted(pos.items()):
        if p.unknown_cost:
            issues.append({"level": "warning", "kind": "cost_unknown", "account": a, "symbol": s, "date": "",
                           "message": f"{s} has shares with no cost", "hint": "Set the price on its IPO / transfer / demerger event so XIRR can include it."})
    for s in sorted({s for (a, s), p in pos.items() if p.qty > EPS}):
        sec = px.get(s)
        if not sec or not sec.last_price:
            issues.append({"level": "warning", "kind": "no_price", "account": "", "symbol": s, "date": "",
                           "message": f"No price for {s}" + (f": {sec.fetch_error}" if sec and sec.fetch_error else ""),
                           "hint": "Run Refresh, or set the Yahoo symbol if the stock was renamed."})
    # 4. the last refresh's cross-checks against Yahoo
    last = session.query(EquityAudit).filter(EquityAudit.kind == "refresh").order_by(EquityAudit.id.desc()).first()
    if last and last.detail:
        for w in json.loads(last.detail).get("warnings", []):
            if not accounts or w.get("account") in accounts or not w.get("account"):
                issues.append({"level": "warning", **w})
    rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (rank[i["level"]], i.get("account", ""), i.get("symbol", ""), i.get("date", "")))
    return issues


def audit(session, account=None):
    accounts = [account] if account and account != "ALL" else None
    pos, problems, canon = replay(session, accounts)
    divs = _dividends(session, accounts)
    issues = reconcile(session, accounts, pos, problems, canon, divs)
    q = session.query(EquityAudit)
    if accounts:
        q = q.filter(EquityAudit.account.in_(accounts + [""]))
    log = [{"id": a.id, "at": a.at, "kind": a.kind, "account": a.account, "file_name": a.file_name,
            "period_from": a.period_from, "period_to": a.period_to, "summary": a.summary}
           for a in q.order_by(EquityAudit.id.desc()).limit(200)]
    checks = []
    hq = session.query(BrokerHolding)
    if accounts:
        hq = hq.filter(BrokerHolding.account.in_(accounts))
    by_acct = defaultdict(list)
    for h in hq:
        by_acct[h.account].append(h)
    for a, rows in sorted(by_acct.items()):
        bad = {i["symbol"] for i in issues if i["kind"] == "holding_mismatch" and i["account"] == a}
        syms = {canon(h.symbol) for h in rows}
        checks.append({"account": a, "as_of": rows[0].as_of, "total": len(syms | bad), "matched": len(syms - bad)})
    return {"issues": issues, "log": log, "holdings_checks": checks}


def stock_detail(session, symbol, account=None):
    accounts = [account] if account and account != "ALL" else None
    pos, _, canon = replay(session, accounts)
    sym = canon(symbol)
    timeline = sorted([t for (a, s), p in pos.items() if s == sym for t in p.timeline], key=lambda t: (t["date"], t["account"]))
    divs = [{"date": d.ex_date, "account": d.account, "qty": d.qty, "dps": d.dps, "amount": d.amount, "source": d.source}
            for d in _dividends(session, accounts) if d.symbol == sym]
    events = [e for e in all_events(session) if canon(e["symbol"]) == sym or canon(e["target_symbol"] or "") == sym]
    return {"symbol": sym, "timeline": timeline, "dividends": divs, "events": events}


def stock_dividends_in_fy(session, fy):
    """Dividends from the stock ledger with an ex-date in financial year `fy` ("FY2025-26"), for the Holdings KPI."""
    y0 = int(fy[2:6])
    rows = session.query(EquityDividend.amount).filter(EquityDividend.ex_date >= f"{y0}-04-01",
                                                       EquityDividend.ex_date <= f"{y0 + 1}-03-31")
    return sum(a for (a,) in rows)


def held_between(pos, sym, start):
    """Accounts that held `sym` at any point on or after `start` (iso)."""
    out = []
    for (a, s), p in pos.items():
        if s != sym:
            continue
        if p.qty > EPS or any(d >= start and q > EPS for d, q in p.qty_steps) or p.qty_before(start) > EPS:
            out.append(a)
    return out


def next_day(d):
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()
