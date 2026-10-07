"""Daily prices for equity (Yahoo Finance, NSE) and mutual funds (AMFI NAV file), plus the scheduler.

Equity and gold ETFs: holdings.ticker (an NSE symbol such as HDFCBANK or GOLDIETF) -> last close, 52-week high / low.
Mutual funds: holdings.scheme_code (AMFI code) and holdings.units -> value = units x NAV. MFs stay stored
as one line (qty 1, cmp = value) so the rest of the app is unchanged; `nav` keeps the latest NAV.
Only holdings with auto_price=1 are touched. Nothing is changed if a source is down: the old value stays
and the reason is kept in holdings.price_note and the run log.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=5d&interval=1d"
YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search?q={}&quotesCount=8&newsCount=0"
HEADERS = {"User-Agent": "Mozilla/5.0 (SpendLens)"}
CLOSE_TIMES = ((19, 0), (22, 30))  # equity closes 15:30; AMFI usually posts the NAV file in the evening


def ensure(db):
    cols = {r[1] for r in db.execute("PRAGMA table_info(holdings)")}
    for name, ddl in (("scheme_code", "TEXT DEFAULT ''"), ("units", "REAL DEFAULT 0"), ("nav", "REAL DEFAULT 0"),
                      ("auto_price", "INTEGER DEFAULT 0"), ("price_date", "TEXT DEFAULT ''"), ("price_note", "TEXT DEFAULT ''")):
        if name not in cols:
            db.execute(f"ALTER TABLE holdings ADD COLUMN {name} {ddl}")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS price_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT, ok INTEGER, updated INTEGER, failed INTEGER, detail TEXT);
        CREATE TABLE IF NOT EXISTS price_history (holding_id INTEGER, price_date TEXT, price REAL, PRIMARY KEY (holding_id, price_date));
    """)
    db.commit()


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


_amfi_cache = {"at": 0.0, "data": {}}


def fetch_amfi(max_age=600):
    """{scheme_code: {name, plan, option, nav, date}} from the AMFI file (kept for 10 minutes so bulk actions download it once)."""
    if _amfi_cache["data"] and time.time() - _amfi_cache["at"] < max_age:
        return _amfi_cache["data"]
    out = {}
    for line in _get(AMFI_URL, 60).splitlines():
        p = line.split(";")
        if len(p) < 8 or not p[0].strip().isdigit():
            continue
        try:
            out[p[0].strip()] = {"name": p[3].strip(), "plan": p[4].strip(), "option": p[5].strip(), "nav": float(p[6]),
                                 "date": datetime.strptime(p[7].strip(), "%d-%b-%Y").date().isoformat()}
        except ValueError:
            continue
    if out:
        _amfi_cache.update(at=time.time(), data=out)
    return out


def scheme_candidates(amfi, name, limit=6):
    spell = lambda x: x.lower().replace("midcap", "mid cap").replace("smallcap", "small cap").replace("largecap", "large cap")
    base = spell(re.sub(r"\(.*?\)", " ", name)).replace("pru ", "prudential ").replace("fof", "fund of fund")
    tokens = [t for t in re.findall(r"[a-z0-9]+", base) if t not in ("fund", "the", "of")]
    if not tokens:
        return []
    scored = []
    for code, s in amfi.items():
        opt = s["option"].lower()
        if "growth" not in opt or "idcw" in opt or "dividend" in opt or "bonus" in opt:
            continue
        hay = spell(s["name"])
        score = sum(t in hay for t in tokens) / len(tokens)
        if score >= 0.7:
            scored.append((score, 1 if s["plan"].lower().startswith("direct") else 0, -len(s["name"]), code))
    scored.sort(reverse=True)
    return [{"code": c, **{k: amfi[c][k] for k in ("name", "plan", "nav", "date")}} for *_, c in scored[:limit]]


def symbol(ticker):
    t = (ticker or "").strip().upper()
    return t if "." in t or "=" in t or t.startswith("^") else f"{t}.NS"


def yahoo_quote(ticker):
    meta = json.loads(_get(YAHOO_CHART.format(urllib.parse.quote(symbol(ticker)))))["chart"]["result"][0]["meta"]
    d = datetime.fromtimestamp(meta["regularMarketTime"]).date().isoformat() if meta.get("regularMarketTime") else date.today().isoformat()
    return {"price": float(meta["regularMarketPrice"]), "high": meta.get("fiftyTwoWeekHigh") or 0, "low": meta.get("fiftyTwoWeekLow") or 0, "date": d,
            "name": meta.get("longName") or meta.get("shortName") or ""}


def yahoo_search(name):
    q = re.sub(r"\b(limited|ltd)\b", "", name, flags=re.I).strip()
    res = json.loads(_get(YAHOO_SEARCH.format(urllib.parse.quote(q)))).get("quotes", [])
    return [{"ticker": r["symbol"].split(".")[0], "name": r.get("longname") or r.get("shortname") or "", "exchange": r.get("exchange")}
            for r in res if r.get("symbol", "").endswith(".NS")]


def run_refresh(db):
    """Update every auto-priced holding. Returns {updated, failed, errors, ran_at}."""
    ensure(db)
    rows = db.execute("SELECT * FROM holdings WHERE auto_price=1").fetchall()
    eq = [r for r in rows if r["asset_type"] in ("EQ", "GOLD") and r["ticker"]]  # listed gold ETFs price like equity
    mf = [r for r in rows if r["asset_type"] == "MF" and r["scheme_code"] and (r["units"] or 0) > 0]
    updated, errors = 0, []

    def quote(r):
        try:
            return r, yahoo_quote(r["ticker"]), None
        except Exception as e:  # network, bad symbol, rate limit ...
            return r, None, str(e)[:120]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(quote, eq))
    for r, q, err in results:
        if q:
            db.execute("UPDATE holdings SET cmp=?, week52_low=?, week52_high=?, price_date=?, price_note='' WHERE id=?",
                       (q["price"], q["low"], q["high"], q["date"], r["id"]))
            db.execute("INSERT OR REPLACE INTO price_history (holding_id, price_date, price) VALUES (?,?,?)", (r["id"], q["date"], q["price"]))
            updated += 1
        else:
            db.execute("UPDATE holdings SET price_note=? WHERE id=?", (err, r["id"]))
            errors.append(f"{r['name']}: {err}")
    if mf:
        try:
            amfi = fetch_amfi(0)  # always fresh for the scheduled run
        except Exception as e:
            amfi, err = {}, str(e)[:120]
            errors.append(f"AMFI: {err}")
            db.executemany("UPDATE holdings SET price_note=? WHERE id=?", [(err, r["id"]) for r in mf])
        for r in mf:
            s = amfi.get(r["scheme_code"])
            if s:
                db.execute("UPDATE holdings SET qty=1, nav=?, cmp=?, price_date=?, price_note='' WHERE id=?",
                           (s["nav"], round(r["units"] * s["nav"], 2), s["date"], r["id"]))
                db.execute("INSERT OR REPLACE INTO price_history (holding_id, price_date, price) VALUES (?,?,?)", (r["id"], s["date"], s["nav"]))
                updated += 1
            elif amfi:
                db.execute("UPDATE holdings SET price_note='scheme code not in AMFI file' WHERE id=?", (r["id"],))
                errors.append(f"{r['name']}: scheme code not found")
    ran = datetime.now().isoformat(timespec="seconds")
    db.execute("INSERT INTO price_runs (ran_at, ok, updated, failed, detail) VALUES (?,?,?,?,?)",
               (ran, 0 if errors and not updated else 1, updated, len(errors), "; ".join(errors)[:1000]))
    db.commit()
    return {"ran_at": ran, "updated": updated, "failed": len(errors), "errors": errors}


def last_ok_run(db):
    r = db.execute("SELECT ran_at FROM price_runs WHERE ok=1 ORDER BY id DESC LIMIT 1").fetchone()
    return datetime.fromisoformat(r["ran_at"]) if r else None


def latest_close(now):
    """Most recent scheduled run time (a weekday 19:00 or 22:30) that is not in the future."""
    d = now.date()
    for back in range(0, 5):
        day = d - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        for h, m in sorted(CLOSE_TIMES, reverse=True):
            t = datetime(day.year, day.month, day.day, h, m)
            if t <= now:
                return t
    return None


def is_stale(db, now=None):
    now = now or datetime.now()
    due, last = latest_close(now), last_ok_run(db)
    return bool(due) and (last is None or last < due)


def start_scheduler(job, every=900):
    """Daemon thread: every 15 minutes, run `job()` if a close time has passed since the last good run.

    Also catches up straight after start-up when the app was closed at the scheduled time.
    """
    def loop():
        time.sleep(20)
        while True:
            try:
                job(only_if_stale=True)
            except Exception as e:  # keep the loop alive whatever happens
                print("price scheduler:", e)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="price-scheduler").start()
