"""Portfolio dashboard maths: snapshots, XIRR, drift, concentration, emergency cover and a goal simulation.

The goal projection is a Monte Carlo simulation (no trained model): every holding group grows at its own
return and volatility, today's SIPs continue (stepping up each year), goals are paid out in their year,
and the P10 / P50 / P90 band plus the chance each goal is fully funded come from the simulated paths.
"""
import json
import random
from datetime import date, timedelta

EMERGENCY = "Emergency Fund"
SIM_PATHS = 1500
CORRELATION = 0.5  # share of each group's yearly shock that comes from one common market factor

DEFAULT_TARGETS = {"Equity": 30, "Mutual Funds": 40, "Gold": 10, "Provident Fund": 10, "Fixed Return": 5, "Emergency Fund": 5}
DEFAULT_ASSUMPTIONS = {
    "stepup": 5,  # yearly rise in SIPs, %
    "groups": {
        "Equity": {"ret": 12, "vol": 18}, "Mutual Funds": {"ret": 12, "vol": 16}, "Gold": {"ret": 8, "vol": 14},
        "Provident Fund": {"ret": 7.1, "vol": 0.5}, "Fixed Return": {"ret": 7, "vol": 0.5},
        "Emergency Fund": {"ret": 6.5, "vol": 0.5}, "Others": {"ret": 8, "vol": 10},
    },
}
# From the LONGTERM PLAN sheet (amounts are future values)
SEED_GOALS = [("Second Car", 1967151, 2034), ("Anaya Higher Education", 5000000, 2038), ("Second Child Education", 6000000, 2045),
              ("Anaya Marriage", 10000000, 2048), ("Second Child Marriage", 12000000, 2055)]


def ensure(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (snap_date TEXT PRIMARY KEY, total REAL, invested REAL, groups TEXT);
        CREATE TABLE IF NOT EXISTS portfolio_goals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, target_amount REAL NOT NULL, target_year INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS portfolio_plan (key TEXT PRIMARY KEY, value TEXT);
    """)
    if not db.execute("SELECT 1 FROM portfolio_plan WHERE key='goals_seeded'").fetchone():
        db.executemany("INSERT INTO portfolio_goals (name, target_amount, target_year) VALUES (?,?,?)", SEED_GOALS)
        db.execute("INSERT INTO portfolio_plan (key, value) VALUES ('goals_seeded', '1')")
        db.commit()


def get_plan(db, key, default):
    r = db.execute("SELECT value FROM portfolio_plan WHERE key=?", (key,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r["value"])
    except ValueError:
        return default


def set_plan(db, key, value):
    db.execute("INSERT INTO portfolio_plan (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
    db.commit()


def group_of(h):
    return h.get("grp") or "Others"


def group_totals(held):
    out = {}
    for h in held:
        g = out.setdefault(group_of(h), {"present": 0.0, "invested": 0.0, "sip": 0.0, "count": 0})
        g["present"] += h["present"]; g["invested"] += h["invested"]; g["sip"] += h.get("sip_amount") or 0; g["count"] += 1
    return {k: {kk: round(vv, 2) if kk != "count" else vv for kk, vv in v.items()} for k, v in out.items()}


def record_snapshot(db, held, today=None):
    ensure(db)
    today = (today or date.today()).isoformat()
    g = group_totals(held)
    db.execute("""INSERT INTO portfolio_snapshots (snap_date, total, invested, groups) VALUES (?,?,?,?)
                  ON CONFLICT(snap_date) DO UPDATE SET total=excluded.total, invested=excluded.invested, groups=excluded.groups""",
               (today, round(sum(h["present"] for h in held), 2), round(sum(h["invested"] for h in held), 2), json.dumps(g)))
    db.commit()


def xirr(flows):
    """flows: [(date, amount)] with outflows negative. Annualised rate as a fraction, or None."""
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = flows[0][0]

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365) for d, a in flows)

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def snapshot_returns(snaps, today):
    """XIRR from the snapshot series (first value in, invested top-ups as flows, latest value out) and the 30-day change."""
    out = {"xirr": None, "span_days": 0, "change": None, "change_pct": None, "since": None}
    if not snaps:
        return out
    first, last = snaps[0], snaps[-1]
    d0, d1 = date.fromisoformat(first["snap_date"]), date.fromisoformat(last["snap_date"])
    out["span_days"], out["since"] = (d1 - d0).days, first["snap_date"]
    if out["span_days"] >= 60:
        flows = [(d0, -first["total"])]
        for a, b in zip(snaps, snaps[1:]):
            top_up = b["invested"] - a["invested"]
            if abs(top_up) > 1:
                flows.append((date.fromisoformat(b["snap_date"]), -top_up))
        flows.append((d1, last["total"]))
        r = xirr(flows)
        out["xirr"] = None if r is None else round(r * 100, 2)
    ref = None
    for s in snaps:
        if date.fromisoformat(s["snap_date"]) <= today - timedelta(days=28):
            ref = s
    if ref and ref["snap_date"] != last["snap_date"]:
        out["change"] = round(last["total"] - ref["total"], 2)
        out["change_pct"] = round(out["change"] / ref["total"] * 100, 2) if ref["total"] else None
    return out


def concentration(held):
    merged = {}
    for h in held:  # several folios of one fund count as one position
        k = h["name"].split(" (Folio")[0].strip()
        m = merged.setdefault(k, {**h, "name": k, "present": 0.0})
        m["present"] += h["present"]
    sectors_src = held
    held = list(merged.values())
    total = sum(h["present"] for h in held) or 1
    ranked = sorted(held, key=lambda h: -h["present"])
    top = ranked[0] if ranked else None
    big = [{"name": h["name"], "pct": round(h["present"] / total * 100, 1)} for h in ranked if h["present"] / total > 0.10]
    sectors = {}
    for h in sectors_src:
        if h["asset_type"] == "EQ":
            s = (_tag_list(h) or [(h.get("sector") or "").strip() or "Other"])[0]  # sector is the equity's first tag
            sectors[s] = sectors.get(s, 0) + h["present"]
    eq = sum(sectors.values()) or 1
    return {
        "top": {"name": top["name"], "pct": round(top["present"] / total * 100, 1)} if top else None,
        "top5_pct": round(sum(h["present"] for h in ranked[:5]) / total * 100, 1),
        "over_10": big,
        "sectors": [{"sector": s, "value": round(v, 2), "pct": round(v / eq * 100, 1)} for s, v in sorted(sectors.items(), key=lambda x: -x[1])],
    }


def drift(groups, targets, total):
    names = list(dict.fromkeys(list(targets) + list(groups)))
    rows = []
    for n in names:
        cur = groups.get(n, {}).get("present", 0)
        tgt = targets.get(n, 0)
        actual = cur / total * 100 if total else 0
        rows.append({"group": n, "value": round(cur, 2), "actual_pct": round(actual, 1), "target_pct": tgt,
                     "drift_pct": round(actual - tgt, 1), "trade": round(tgt / 100 * total - cur, 0)})
    return sorted(rows, key=lambda r: -r["value"])


def performers(held):
    live = [h for h in held if h["asset_type"] in ("EQ", "MF", "GOLD") and h["invested"] > 0]
    by_pct = sorted(live, key=lambda h: -h["pl_pct"])
    pick = lambda h: {"name": h["name"], "type": h["asset_type"], "invested": h["invested"], "present": h["present"], "pl": h["pl"], "pl_pct": h["pl_pct"]}
    return {"best": [pick(h) for h in by_pct[:5]], "worst": [pick(h) for h in by_pct[::-1][:5] if h["pl_pct"] < 0 or len(by_pct) > 5]}


def fixed_income(held):
    rated = [h for h in held if h.get("rate") and h["rate"] > 0 and h["present"] > 0]
    w = sum(h["present"] for h in rated)
    soon = []
    for h in held:
        try:
            m = date.fromisoformat(h.get("maturity") or "")
        except ValueError:
            continue
        if date.today() <= m <= date.today() + timedelta(days=365):
            soon.append({"name": h["name"], "date": m.isoformat(), "value": h["present"]})
    return {"avg_rate": round(sum(h["rate"] * h["present"] for h in rated) / w, 2) if w else None,
            "rated_value": round(w, 2), "maturing": sorted(soon, key=lambda x: x["date"])}


def monthly_spend(db, today):
    """Average spend of the last three complete months that have data."""
    cur = today.strftime("%Y-%m")
    rows = db.execute("""SELECT substr(date,1,7) m, SUM(amount - COALESCE(cashback,0)) s FROM expenses
                         WHERE substr(date,1,7) < ? GROUP BY m HAVING s > 0 ORDER BY m DESC LIMIT 3""", (cur,)).fetchall()
    return sum(r["s"] for r in rows) / len(rows) if rows else 0


def simulate(groups, goals, assumptions, today=None, seed=7, paths=SIM_PATHS):
    """Monte Carlo of the investable corpus (everything except the emergency fund) against the goals."""
    today = today or date.today()
    ag = assumptions["groups"]
    stepup = assumptions.get("stepup", 0) / 100
    names = [g for g in groups if g != EMERGENCY and (groups[g]["present"] > 0 or groups[g].get("sip", 0) > 0)]
    start = {g: groups[g]["present"] for g in names}
    sip = {g: groups[g]["sip"] * 12 for g in names}
    goals = sorted(goals, key=lambda g: g["target_year"])
    if not names:
        return None
    pay = {}
    for g in goals:
        pay.setdefault(max(g["target_year"] - today.year, 1), []).append(g)
    horizon = max([k for k in pay] + [10])
    horizon = min(horizon, 40)
    rng = random.Random(seed)
    years = [[] for _ in range(horizon + 1)]
    ok = {g["id"]: 0 for g in goals}
    for _ in range(paths):
        bal = dict(start)
        years[0].append(sum(bal.values()))
        for k in range(1, horizon + 1):
            market = rng.gauss(0, 1)
            for g in names:
                a = ag.get(g) or ag["Others"]
                z = CORRELATION ** 0.5 * market + (1 - CORRELATION) ** 0.5 * rng.gauss(0, 1)
                r = max(a["ret"] / 100 + a["vol"] / 100 * z, -0.6)
                bal[g] = bal[g] * (1 + r) + sip[g] * (1 + stepup) ** (k - 1) * (1 + r) ** 0.5
            for goal in pay.get(k, []):
                total = sum(bal.values())
                if total >= goal["target_amount"]:
                    ok[goal["id"]] += 1
                    take = goal["target_amount"]
                else:
                    take = total
                for g in names:  # pay pro rata from every group
                    bal[g] -= take * (bal[g] / total) if total else 0
            years[k].append(sum(bal.values()))
    pct = lambda xs, q: sorted(xs)[min(int(len(xs) * q), len(xs) - 1)]
    band = [{"year": today.year + k, "p10": round(pct(v, .1)), "p50": round(pct(v, .5)), "p90": round(pct(v, .9))} for k, v in enumerate(years)]
    return {
        "band": band,
        "start": round(sum(start.values())),
        "monthly_sip": round(sum(sip.values()) / 12),
        "goals": [{**g, "probability": round(ok[g["id"]] / paths * 100)} for g in goals],
        "paths": paths,
    }


def required_extra_sip(groups, goals, assumptions, today=None, floor=70):
    """Smallest extra monthly SIP (spread over current SIPs; simple search) for every goal to reach `floor`% odds."""
    base = sum(g["sip"] for n, g in groups.items() if n != EMERGENCY)
    scale_names = [n for n, g in groups.items() if n != EMERGENCY]
    if not goals or not scale_names:
        return 0

    def lowest(extra):
        gs = {n: dict(g) for n, g in groups.items()}
        w = sum(gs[n]["present"] for n in scale_names) or 1
        for n in scale_names:
            gs[n]["sip"] = gs[n]["sip"] + extra * gs[n]["present"] / w
        res = simulate(gs, goals, assumptions, today, paths=400)
        return min(g["probability"] for g in res["goals"])

    if lowest(0) >= floor:
        return 0
    lo, hi = 0, max(base * 3, 100000)
    for _ in range(9):
        mid = (lo + hi) / 2
        if lowest(mid) >= floor:
            hi = mid
        else:
            lo = mid
    return int(round(hi / 1000.0) * 1000)


_cache = {}


def projection(groups, goals, assumptions, today=None):
    """Expected + conservative simulation and the extra SIP needed, cached until the inputs change meaningfully."""
    today = today or date.today()
    key = json.dumps([{g: [round(v["present"], -4), round(v["sip"], -2)] for g, v in groups.items()}, goals, assumptions, today.isoformat()], sort_keys=True, default=str)
    if key in _cache:
        return _cache[key]
    sim = simulate(groups, goals, assumptions, today)
    out = None
    if sim:
        cons = {"stepup": 0, "groups": {k: {"ret": max(v["ret"] - 3, 0), "vol": v["vol"]} for k, v in assumptions["groups"].items()}}
        low = simulate(groups, goals, cons, today, paths=600)
        for g, c in zip(sim["goals"], low["goals"]):
            g["conservative"] = c["probability"]
        sim["conservative_band"] = low["band"]
        out = (sim, required_extra_sip(groups, goals, assumptions, today) if goals else 0)
    _cache.clear()
    _cache[key] = out or (None, 0)
    return _cache[key]


# ---------------------------------------------------------------- exposure (what the money is really in)
EXPOSURES = ["Equity", "Gold", "Debt", "Cash"]
_EXTRA_LABELS = {"elss": "ELSS (Tax saver)", "arbritage": "Arbitrage", "arbitrage": "Arbitrage"}


def guess_exposure(h):
    """(exposure, uncertain) from the instrument type and the name. Uncertain guesses are listed for review."""
    t, name = h.get("asset_type"), (h.get("name") or "").lower()
    if t == "EQ":
        return "Equity", False
    if t == "GOLD" or "gold" in name:
        return "Gold", False
    if t in ("FD", "PF"):
        return "Debt", False
    if t == "CASH":
        return "Cash", False
    if t == "MF":
        if "arbitrage" in name or "arbritage" in name:
            return "Debt", True  # taxed like equity but earns like debt
        if any(k in name for k in ("liquid", "overnight", "money market")):
            return "Cash", True
        if any(k in name for k in ("debt", "gilt", "bond", "income", "short term", "corporate")):
            return "Debt", True
        if any(k in name for k in ("cap", "elss", "equity", "index", "nifty", "sensex", "flexi", "value", "focused")):
            return "Equity", False
        return "Equity", True
    return "Equity", True


def seed_exposure(db):
    """Fill the exposure (and a first set of tags) on holdings that have none. Never overwrites what you set."""
    rows = db.execute("SELECT id, name, asset_type, sector, tags, exposure, grp FROM holdings").fetchall()
    for r in rows:
        h = dict(r)
        sets = {}
        if not h["exposure"]:
            sets["exposure"] = guess_exposure(h)[0]
        if not (h["tags"] or "").strip():
            label = (h["sector"] or "").strip()
            if h["asset_type"] in ("EQ", "MF") and label:
                sets["tags"] = _EXTRA_LABELS.get(label.lower(), label.title())
            elif h["grp"] == EMERGENCY:
                sets["tags"] = "Emergency"
        if sets:
            db.execute(f"UPDATE holdings SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), h["id"]))
    db.commit()


def _tag_list(h):
    return [t.strip() for t in (h.get("tags") or "").split(",") if t.strip()]


def exposure_summary(held, targets):
    """Allocation by exposure (sums to 100%), exposure x group, tag breakdown and holdings whose exposure is a guess."""
    total = sum(h["present"] for h in held) or 0
    rows, by_group, tags = {}, {}, {}
    for h in held:
        e = mix_of(h)
        r = rows.setdefault(e, {"present": 0.0, "invested": 0.0, "count": 0})
        r["present"] += h["present"]; r["invested"] += h["invested"]; r["count"] += 1
        g = by_group.setdefault(group_of(h), {})
        g[e] = g.get(e, 0) + h["present"]
        for t in _tag_list(h):
            x = tags.setdefault(t, {"present": 0.0, "count": 0, "exposures": {}})
            x["present"] += h["present"]; x["count"] += 1
            x["exposures"][e] = x["exposures"].get(e, 0) + h["present"]
    out = []
    for e in MIX:
        r = rows.get(e, {"present": 0.0, "invested": 0.0, "count": 0})
        pct = round(r["present"] / total * 100, 1) if total else 0
        tgt = (targets or {}).get(e)
        pl = r["present"] - r["invested"]
        out.append({"name": e, "present": round(r["present"], 2), "invested": round(r["invested"], 2), "pl": round(pl, 2),
                    "pl_pct": round(pl / r["invested"] * 100, 1) if r["invested"] else 0, "pct": pct, "count": r["count"],
                    "target": tgt, "drift": None if tgt is None else round(pct - tgt, 1),
                    "add": None if tgt is None else round(tgt / 100 * total - r["present"], 0)})
    tag_rows = sorted(({"tag": t, "present": round(x["present"], 2), "count": x["count"],
                        "pct": round(x["present"] / total * 100, 1) if total else 0,
                        "exposure": max(x["exposures"], key=x["exposures"].get)} for t, x in tags.items()), key=lambda x: -x["present"])
    groups = [{"group": g, "values": {k: round(v, 2) for k, v in vals.items()}}
              for g, vals in sorted(by_group.items(), key=lambda kv: -sum(kv[1].values()))]
    return {"total": round(total, 2), "exposures": out, "by_group": groups, "tags": tag_rows, "targets": targets or {}}


# ---------------------------------------------------------------- SIP mix: split, forecast and the way to a target ratio
MIX = ["Equity", "Gold", "Debt"]  # Cash counts as Debt here
DEFAULT_MIX_TARGETS = {"Equity": 60, "Gold": 10, "Debt": 30}
DEFAULT_MIX_RETURNS = {"Equity": 12, "Gold": 8, "Debt": 7}
DEFAULT_MIX_YEARS = 15
DEFAULT_REACH_YEARS = 5  # by when the ratio should be reached
MAX_MONTHS = 360


def mix_of(h):
    e = h.get("exposure") or guess_exposure(h)[0]
    return e if e in ("Equity", "Gold") else "Debt"


def mix_plan(db):
    """Target ratio (admin), expected returns, horizon and the yearly SIP step-up."""
    t = get_plan(db, "mix_targets", None)
    if not t:
        old = get_plan(db, "exposure_targets", {}) or {}
        t = {"Equity": old.get("Equity", 0), "Gold": old.get("Gold", 0), "Debt": old.get("Debt", 0) + old.get("Cash", 0)} if old else dict(DEFAULT_MIX_TARGETS)
    s = sum(t.values()) or 100
    t = {e: round(t.get(e, 0) / s * 100, 2) for e in MIX}
    return {"targets": t, "returns": {**DEFAULT_MIX_RETURNS, **get_plan(db, "mix_returns", {})},
            "years": get_plan(db, "mix_years", DEFAULT_MIX_YEARS), "reach_years": get_plan(db, "mix_reach_years", DEFAULT_REACH_YEARS), "stepup": get_plan(db, "assumptions", DEFAULT_ASSUMPTIONS).get("stepup", 0)}


def _rm(r):
    return (1 + r / 100) ** (1 / 12) - 1


def _add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def _solve_split(A, K, S, t):
    """SIP shares x (sum 1, none negative) so that start-growth A + x*S*K ends in ratio t. Returns (x, exact).
    An exposure already above its target would need a negative SIP (a sale), so it is held at 0 and the rest re-solved."""
    free = list(MIX)
    V = 0.0
    while free:
        den = sum(t[e] / (S * K[e]) for e in free)
        if den <= 0:
            break
        V = (1 + sum(A[e] / (S * K[e]) for e in free)) / den
        neg = [e for e in free if t[e] * V - A[e] < 0]
        if not neg:
            break
        free = [e for e in free if e not in neg]
    if not free or sum(t[e] for e in free) <= 0:
        return dict(t), False
    x = {e: (t[e] * V - A[e]) / (S * K[e]) if e in free else 0.0 for e in MIX}
    tot = sum(x.values()) or 1
    return {e: x[e] / tot for e in MIX}, len(free) == len(MIX)


def _simulate_mix(start, S, split_at, returns, stepup, months):
    """Month-by-month balances per exposure; split_at(m) gives the SIP shares of month m (1-based)."""
    rm = {e: _rm(returns[e]) for e in MIX}
    bal = dict(start)
    out = [dict(bal)]
    for m in range(1, months + 1):
        sip = S * (1 + stepup / 100) ** ((m - 1) // 12)
        sp = split_at(m)
        bal = {e: bal[e] * (1 + rm[e]) + sip * sp[e] for e in MIX}
        out.append(dict(bal))
    return out


def _pct(b):
    t = sum(b.values())
    return {e: round(b[e] / t * 100, 2) if t else 0 for e in MIX}


def mix_summary(held, plan, today=None):
    today = today or date.today()
    t, ret, stepup = plan["targets"], plan["returns"], plan["stepup"]
    start = {e: 0.0 for e in MIX}
    sip = {e: 0.0 for e in MIX}
    items = {e: [] for e in MIX}
    for h in held:
        e = mix_of(h)
        start[e] += h["present"]
        sip[e] += h.get("sip_amount") or 0
        if h.get("sip_amount"):
            items[e].append({"id": h["id"], "name": h["name"], "ticker": h.get("ticker") or "", "asset_type": h["asset_type"], "grp": group_of(h), "amt": round(h["sip_amount"], 2)})
    S, total = sum(sip.values()), sum(start.values())
    cur_x = {e: sip[e] / S if S else 0 for e in MIX}
    out = {"targets": t, "returns": ret, "years": plan["years"], "stepup": stepup,
           "current": {"total": round(total, 2), "value": {e: round(start[e], 2) for e in MIX}, "pct": _pct(start)},
           "sip": {"total": round(S, 2), "by": {e: {"amt": round(sip[e], 2), "pct": round(cur_x[e] * 100, 1), "items": sorted(items[e], key=lambda i: -i["amt"])} for e in MIX}}}
    if not total and not S:
        return {**out, "plan": None, "path": [], "forecast": []}

    # Solve for every possible month N: with the SIP shares x that make the mix hit the target at month N, is x non-negative?
    # The first N that works is the earliest possible date; the split used is the one for the date you chose (a gentler move),
    # or the earliest possible date if yours is too soon.
    tshare = {e: t[e] / 100 for e in MIX}
    want = int(min(round(plan["reach_years"] * 12), MAX_MONTHS))
    reach, split, earliest, results = None, None, None, {}
    now = _pct(start)
    if all(abs(now[e] - t[e]) <= 0.5 for e in MIX):
        reach, split, earliest = 0, dict(tshare), 0
    elif S > 0:
        A = dict(start)
        K = {e: 0.0 for e in MIX}
        for n in range(1, MAX_MONTHS + 1):
            g = (1 + stepup / 100) ** ((n - 1) // 12)
            for e in MIX:
                A[e] *= 1 + _rm(ret[e])
                K[e] = K[e] * (1 + _rm(ret[e])) + g
            results[n] = _solve_split(A, K, S, tshare)
            if earliest is None and results[n][1]:
                earliest = n
        if earliest is not None:
            reach = max(earliest, want)
            if not results[reach][1]:
                reach = earliest
            split = results[reach][0]
        else:
            split = results[want][0]
    split = split or dict(tshare)

    horizon = min(max(int(round(plan["years"] * 12)), (reach or 0) + 12), MAX_MONTHS)
    rec_split = lambda m: split if (reach is None or m <= reach) else tshare
    rec = _simulate_mix(start, S, rec_split, ret, stepup, horizon)
    cur = _simulate_mix(start, S, lambda m: cur_x, ret, stepup, horizon)
    base = today.replace(day=1)
    def sip_in(m, sp):  # rupees sent to each exposure in month m (None before the first month)
        return {e: round(S * (1 + stepup / 100) ** ((m - 1) // 12) * sp[e]) for e in MIX} if m >= 1 else None

    path = [{"m": i, "date": _add_months(base, i).isoformat(), "rec": _pct(rec[i]), "cur": _pct(cur[i]),
             "sip_rec": sip_in(i, rec_split(i)), "sip_cur": sip_in(i, cur_x)} for i in range(horizon + 1)]
    forecast = [{"year": _add_months(base, m).year, "months": m,
                 "values": {e: round(rec[m][e]) for e in MIX}, "total": round(sum(rec[m].values())),
                 "pct": _pct(rec[m]), "current_total": round(sum(cur[m].values()))}
                for m in range(12, horizon + 1, 12)]
    recommended = {e: {"amt": round(S * split[e]), "pct": round(split[e] * 100, 1), "delta": round(S * split[e] - sip[e])} for e in MIX}
    out["plan"] = {"reach_month": reach, "reach_date": _add_months(base, reach).isoformat() if reach is not None else None,
                   "reachable": reach is not None, "wanted_months": want,
                   "earliest_month": earliest, "earliest_date": _add_months(base, earliest).isoformat() if earliest is not None else None,
                   "recommended": recommended,
                   "after": {e: {"amt": round(S * tshare[e]), "pct": round(t[e], 1)} for e in MIX},
                   "end_mix": _pct(rec[horizon]), "horizon_months": horizon}
    out["path"] = path
    out["forecast"] = forecast
    return out
