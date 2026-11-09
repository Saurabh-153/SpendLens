"""The Refresh button behind the stock ledger: fetches each stock's price, split history and dividend history from
Yahoo, then reconciles them with what the broker's files say.

- Splits Yahoo lists that no event explains yet are added as SPLIT events (source "yahoo"), so share counts follow.
  Splits after a stock was exited are added too (the replay skips them, nothing is held), so an exit price can be
  compared with today's price on the same basis.
- Yahoo's dividends are split-adjusted (Bajaj Finance's ₹30 in 2023 shows as ₹3.0), so each is multiplied back by the
  market-wide splits and bonuses after its ex-date before use.
- Where an account's dividend statement covers the date, the statement wins: Yahoo is only compared with it, and a
  payout the statement lacks, or a different per-share amount, becomes a warning in the audit.
- After the statement's last day (and from 2023 for an account with no statement) Yahoo's dividends are stored for the
  shares the account held at the end of the day before the ex-date. Later statement imports replace them.

Every refresh writes one equity_audit row with what it added, changed, removed and doubted.
"""
import json
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import equity as eq
from db.models import EquityAudit, EquityDividend, EquityEvent, EquitySecurity
from prices import _get

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{}?period1=1483228800&period2={}&interval=1mo&events=div%2Csplit"
FETCH_FROM = "2023-01-01"
MATCH_DAYS = 10


def fetch(yahoo_symbol):
    """{price, price_date, name, dividends: [(iso, amount)], splits: [(iso, new, old)]} from Yahoo's chart API."""
    url = CHART.format(urllib.parse.quote(yahoo_symbol), int(datetime.now(timezone.utc).timestamp()) + 86400)
    res = json.loads(_get(url, 20))["chart"]["result"][0]
    meta, ev = res["meta"], res.get("events") or {}
    off = int(meta.get("gmtoffset") or 19800)

    def day(ts):
        return datetime.fromtimestamp(int(ts) + off, tz=timezone.utc).date().isoformat()
    return {
        "price": float(meta["regularMarketPrice"]) if meta.get("regularMarketPrice") else None,
        "price_date": day(meta["regularMarketTime"]) if meta.get("regularMarketTime") else date.today().isoformat(),
        "name": meta.get("longName") or meta.get("shortName") or "",
        "dividends": sorted((day(v["date"]), float(v["amount"])) for v in (ev.get("dividends") or {}).values()),
        "splits": sorted((day(v["date"]), float(v["numerator"]), float(v["denominator"])) for v in (ev.get("splits") or {}).values()),
    }


def _fetch_one(sym, override):
    tries = [override] if override else [f"{sym}.NS", f"{sym}.BO"]
    err = ""
    for y in tries:
        try:
            return sym, y, fetch(y), ""
        except Exception as e:  # network or unknown symbol: try the next exchange, then report
            err = f"{y}: {str(e)[:80]}"
    return sym, tries[-1], None, err


def _near(a, b, days=MATCH_DAYS):
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= days


def refresh(session, today=None):
    today = (today or date.today()).isoformat()
    pos, _, canon = eq.replay(session)
    syms = sorted({s for (_, s) in pos} | {d.symbol for d in session.query(EquityDividend.symbol).distinct()})
    secs = {s.symbol: s for s in session.query(EquitySecurity)}
    overrides = {s: (secs[s].yahoo_symbol if s in secs else "") for s in syms}   # plain strings: workers never touch ORM objects
    with ThreadPoolExecutor(8) as ex:   # network only; the session is used on this thread alone
        fetched = list(ex.map(lambda s: _fetch_one(s, overrides[s]), syms))

    errors, data = [], {}
    for sym, ysym, d, err in fetched:
        sec = secs.get(sym)
        if sec is None:
            sec = EquitySecurity(symbol=sym)
            session.add(sec)
            secs[sym] = sec
        if d is None:
            sec.fetch_error = err
            errors.append({"symbol": sym, "error": err})
            continue
        data[sym] = d
        sec.fetch_error = ""
        if d["price"]:
            sec.last_price, sec.price_date = d["price"], d["price_date"]
        if d["name"]:
            sec.name = d["name"]

    # 1. splits Yahoo knows that no event covers yet
    events = eq.all_events(session)
    added_splits = []
    for sym, d in data.items():
        for when, new, old in d["splits"]:
            if new <= 0 or old <= 0 or abs(new / old - 1) < 1e-9:
                continue
            f = new / old
            dup = any(canon(e["symbol"]) == sym and e["kind"] in ("SPLIT", "BONUS") and _near(e["ex_date"], when)
                      and abs(eq.factor(e) - f) / f < 0.01 for e in events)
            ps = [p for (a, s), p in pos.items() if s == sym]
            held = any(p.qty_before(when) > eq.EPS for p in ps)
            # also after an exit: today's price is then compared with a split-adjusted exit price
            after_exit = not held and any(p.first and p.first < when for p in ps)
            if dup or not (held or after_exit):
                continue
            e = EquityEvent(account="", symbol=sym, ex_date=when, kind="SPLIT", ratio_new=new, ratio_old=old, source="yahoo",
                            note="from Yahoo's split history" + (" (after you exited)" if after_exit else ""))
            session.add(e)
            added_splits.append([sym, when, f"{new:g}:{old:g}"])
    if added_splits:
        session.flush()
        pos, _, canon = eq.replay(session)
        events = eq.all_events(session)

    # 2. dividends
    cov = eq.coverage(session)
    accounts = eq.account_list(session)
    # Yahoo adjusts its dividends by every split it lists (including ones after the user exited, which are not added
    # as events), plus actions it doesn't list (Bajaj Finance's bonus). Undo with Yahoo's list plus the market-wide
    # events that don't match one of its splits.
    market = defaultdict(list)
    for sym, d in data.items():
        for when, new, old in d["splits"]:
            if new > 0 and old > 0:
                market[sym].append({"kind": "SPLIT", "ex_date": when, "ratio_new": new, "ratio_old": old})
    for e in events:
        if e["kind"] in ("SPLIT", "BONUS") and not e["account"]:
            sym = canon(e["symbol"])
            f = eq.factor(e)
            if not any(_near(y["ex_date"], e["ex_date"]) and abs(eq.factor(y) - f) / f < 0.01 for y in market[sym]):
                market[sym].append(e)
    stmt = defaultdict(lambda: defaultdict(float))   # (account, symbol) -> {date: sum of dps}
    for r in session.query(EquityDividend).filter(EquityDividend.source == "zerodha"):
        stmt[(r.account, r.symbol)][r.ex_date] += r.dps

    warnings, want = [], {}
    for sym, d in data.items():
        per_day = defaultdict(float)
        for when, amt in d["dividends"]:
            per_day[when] += amt
        for when, amt in sorted(per_day.items()):
            f = 1.0
            for e in market.get(sym, []):
                if e["ex_date"] > when:
                    f *= eq.factor(e)
            dps = round(amt * f, 4)
            for a in accounts:
                p = pos.get((a, sym))
                q = p.qty_before(when) if p else 0.0
                if q <= eq.EPS:
                    continue
                to = cov.get(a, {}).get("statement_to")
                if to and when <= to:
                    rows = stmt.get((a, sym), {})
                    match = [dd for dd in rows if _near(dd, when, 3)]
                    if when < FETCH_FROM:
                        continue
                    if not match:
                        warnings.append({"kind": "missing_dividend", "account": a, "symbol": sym, "date": when,
                                         "message": f"Yahoo shows ₹{dps:g}/share on {when} while {a} held {q:g}; the statement has no row",
                                         "hint": "Either the statement is incomplete or a share count before this date is wrong."})
                    else:
                        s = sum(rows[dd] for dd in match)
                        if abs(s - dps) > max(0.02 * s, 0.01):
                            warnings.append({"kind": "dps_mismatch", "account": a, "symbol": sym, "date": when,
                                             "message": f"Statement ₹{s:g}/share vs Yahoo ₹{dps:g}/share (after undoing splits)",
                                             "hint": "A split or bonus after this date is missing or wrong in Corporate actions."})
                    continue
                if when < FETCH_FROM:
                    continue
                want[(a, sym, when, dps)] = round(q, 4)

    # store: diff the wanted Yahoo rows against the ones already there (only for symbols fetched this time)
    have = {(r.account, r.symbol, r.ex_date, r.dps): r for r in session.query(EquityDividend).filter(EquityDividend.source == "yahoo")
            if r.symbol in data}
    added, updated, removed = [], [], []
    for k, q in want.items():
        a, sym, when, dps = k
        amt = round(q * dps, 2)
        r = have.pop(k, None)
        if r is None:
            session.add(EquityDividend(account=a, symbol=sym, ex_date=when, qty=q, dps=dps, amount=amt, source="yahoo", raw_symbol=sym))
            added.append([a, sym, when, q, dps, amt])
        elif abs(r.qty - q) > 1e-6 or abs(r.amount - amt) > 0.005:
            updated.append([a, sym, when, r.qty, q, r.amount, amt])
            r.qty, r.amount, r.updated_at = q, amt, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for r in have.values():
        removed.append([r.account, r.symbol, r.ex_date, r.amount])
        session.delete(r)

    summary = (f"{len(data)} of {len(syms)} stocks fetched; {len(added_splits)} splits added; dividends "
               f"{len(added)} added, {len(updated)} updated, {len(removed)} removed; {len(warnings)} warnings")
    session.add(EquityAudit(kind="refresh", period_to=today, summary=summary,
                            detail=json.dumps({"errors": errors, "splits_added": added_splits, "dividends_added": added,
                                               "dividends_updated": updated, "dividends_removed": removed, "warnings": warnings})))
    session.commit()
    return {"summary": summary, "fetched": len(data), "failed": len(errors), "errors": errors[:20], "splits_added": added_splits,
            "dividends_added": len(added), "dividends_updated": len(updated), "dividends_removed": len(removed),
            "warnings": len(warnings), "ran_at": (datetime.now(timezone.utc) - timedelta(0)).isoformat(timespec="seconds")}
