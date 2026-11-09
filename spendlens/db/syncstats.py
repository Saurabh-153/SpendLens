"""The numbers behind Settings › Database: the KPIs, both databases side by side, the table-by-table view, the
comparison you can run by hand, and the abnormalities flagged automatically. Reads db/failover.py's state and the
sync log (db/synclog.py); the only thing it writes is a comparison's result into that log."""
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, inspect, select, table, text

from .replicate import SKIP, table_digest

AREAS = {
    "Expense & budget": ["expenses", "categories", "subcategories", "subcategory_rules", "category_targets",
                         "budget_history", "settings"],
    "Portfolio": ["holdings", "transactions", "sip_log", "price_history", "price_runs", "portfolio_snapshots",
                  "holding_snapshots", "portfolio_goals", "portfolio_plan", "holding_groups", "app_prefs"],
    "MF analysis": ["mf_sources", "mf_fund_months", "mf_holdings", "mf_reports"],
    "Stock ledger": ["equity_trades", "equity_events", "equity_dividends", "broker_holdings", "equity_securities",
                     "equity_audit"],
    "Credit cards": ["card_txns", "card_statements", "cards", "card_accounts", "card_merchant_rules", "card_perks"],
    "Calendar": ["reminders", "reminder_categories", "reminder_settings", "reminder_overrides", "vacations",
                 "trackers", "tracker_days", "tracker_cost_links"],
}
_AREA_OF = {t: a for a, ts in AREAS.items() for t in ts}
NAME = {"postgresql": "PostgreSQL", "sqlite": "SQLite"}
STALE_AFTER_S = 120          # saves waiting this long without a copy is unusual (the copy runs ~10 s after a save)
LARGE_REMOVAL = (20, 0.2)    # a table losing at least 20 rows and 20 % of them in one copy is worth a look
FAILURE_RATE = 0.05
SLOW_MS = 30_000


def _ago(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() if iso else None


def _counts(engine):
    """{table: rows}, or None if the database can't be reached."""
    try:
        with engine.connect() as c:
            names = [n for n in inspect(c).get_table_names() if n not in SKIP]
            return {n: c.execute(select(func.count()).select_from(table(n))).scalar() for n in names}
    except Exception:
        return None


def _ping(engine):
    t0 = time.monotonic()
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True, round((time.monotonic() - t0) * 1000)
    except Exception:
        return False, None


def _size(engine, path=None):
    try:
        if engine.dialect.name == "postgresql":
            with engine.connect() as c:
                return c.execute(text("SELECT pg_database_size(current_database())")).scalar()
        return sum(os.path.getsize(p) for p in (path, f"{path}-wal") if p and os.path.exists(p))
    except Exception:
        return None


def _engines(fo):
    """(main engine, copy engine, copy engine is temporary) for whichever database is main right now."""
    if fo.kind == "postgresql":
        if not fo.mirror.exists():
            return fo.primary, None, False
        uri = Path(fo.mirror.path).as_uri()
        return fo.primary, create_engine(f"sqlite:///{uri}?mode=ro&uri=true"), True
    return fo._sqlite_main_engine(), fo.primary, False


def _syncer(fo):
    return fo.mirror if fo.kind == "postgresql" else fo._sync_to_postgres()


def _db_card(kind, engine, role, fo, counts):
    up, ms = _ping(engine) if engine is not None else (False, None)
    path = fo.mirror.path if kind == "sqlite" else None
    where = os.path.relpath(path, os.path.dirname(os.path.dirname(path))) if path else \
        f"{engine.url.host}:{engine.url.port} / {engine.url.database}"
    return {"kind": kind, "name": NAME[kind], "role": role, "reachable": up, "latency_ms": ms,
            "rows": sum(counts.values()) if counts else None, "tables": len(counts) if counts else None,
            "size_bytes": _size(engine, path) if up else None, "where": where.replace(os.sep, "/")}


def abnormalities(fo, log, main_counts, copy_counts, syncer, last, last_ok, week):
    """What looks wrong right now, most serious first: [{level, title, detail}]."""
    out = []
    copy_name, main_name = NAME[_other(fo.kind)], NAME[fo.kind]
    if fo.read_only():
        out.append(("critical", "PostgreSQL can't be reached",
                    "The app is showing the SQLite copy, read-only. Switch to SQLite to keep saving."))
    fails = log.consecutive_failures()
    if last and not last["ok"]:
        out.append(("critical", f"{fails} sync{'s' if fails > 1 else ''} in a row failed" if fails > 1 else "The last sync failed",
                    f"{last['error'] or 'unknown error'}. The copy in {copy_name} is from "
                    f"{_fmt_ago(last_ok and last_ok['at'])}; the next sync tries again."))
    if main_counts and copy_counts is not None and syncer.pending == 0 and not syncer._run_lock.locked():
        differ = [t for t in main_counts if main_counts.get(t) != copy_counts.get(t)]
        if differ:
            out.append(("critical", f"Row counts differ in {len(differ)} table{'s' if len(differ) > 1 else ''}",
                        f"{', '.join(differ[:5])}{' and more' if len(differ) > 5 else ''}: {main_name} and {copy_name} "
                        "should match with nothing waiting to sync. Run Compare now, then check the sync log."))
    cmp = log.last_compare()
    if cmp and not cmp["ok"] and not cmp["pending"] and (not last_ok or last_ok["at"] <= cmp["at"]):
        out.append(("critical", f"The last comparison found {cmp['differs']} different table{'s' if cmp['differs'] != 1 else ''}",
                    f"Found at {_fmt_time(cmp['at'])} with no saves waiting. Run Compare now again after the next sync."))
    if copy_counts is None:
        out.append(("warning", f"{copy_name} (the copy) can't be read",
                    "Saves still work; the copy will catch up once it is reachable again."))
    age = _ago(last_ok and last_ok["at"])
    if syncer.pending and (age is None or age > STALE_AFTER_S):
        out.append(("warning", f"{syncer.pending} save{'s' if syncer.pending > 1 else ''} not copied yet",
                    f"The last good copy is from {_fmt_ago(last_ok and last_ok['at'])}; copies normally follow a save within ~10 s."))
    elif not fo.read_only() and (age is None or age > 2 * syncer.period):
        out.append(("warning", "No successful sync recently", f"Last good copy: {_fmt_ago(last_ok and last_ok['at'])}."))
    if last_ok and last_ok.get("detail"):
        for name, (rows, added, changed, removed) in last_ok["detail"].items():
            before = rows - added + removed
            if removed >= LARGE_REMOVAL[0] and before and removed / before >= LARGE_REMOVAL[1]:
                out.append(("warning", f"{name} lost {removed:,} rows in one sync",
                            f"From {before:,} to {rows:,} rows ({removed / before:.0%}) at {_fmt_time(last_ok['at'])}. "
                            "If you didn't delete them, check before the next switch."))
    if week["syncs"] >= 10 and week["failed"] / week["syncs"] > FAILURE_RATE:
        out.append(("warning", f"{week['failed']} of {week['syncs']} syncs failed in the last 7 days",
                    "More than 5 %. The sync log shows why."))
    if last and last["ok"] and (last["duration_ms"] or 0) > SLOW_MS:
        out.append(("info", "The last sync was slow", f"It took {last['duration_ms'] / 1000:.0f} s."))
    rank = {"critical": 0, "warning": 1, "info": 2}
    return [{"level": lvl, "title": t, "detail": d} for lvl, t, d in sorted(out, key=lambda x: rank[x[0]])]


def _other(kind):
    return "sqlite" if kind == "postgresql" else "postgresql"


def _fmt_time(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%d %b, %H:%M") if iso else "never"


def _fmt_ago(iso):
    s = _ago(iso)
    if s is None:
        return "never"
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{round(s / 60)} min ago"
    return _fmt_time(iso)


def overview(fo):
    log, syncer = fo.log, _syncer(fo)
    main_eng, copy_eng, temp = _engines(fo)
    try:
        main_counts = None if fo.read_only() else _counts(main_eng)
        copy_counts = _counts(copy_eng) if copy_eng is not None else None
        main = _db_card(fo.kind, main_eng, "main", fo, main_counts)
        copy = _db_card(_other(fo.kind), copy_eng, "copy", fo, copy_counts) if copy_eng is not None else \
            {"kind": _other(fo.kind), "name": NAME[_other(fo.kind)], "role": "copy", "reachable": False}
    finally:
        if temp:
            copy_eng.dispose()
    main["last_save_at"] = fo.last_save_at
    copy["updated_at"] = syncer.status().get("updated_at")
    copy["last_error"] = syncer.status().get("last_error")
    last, last_ok = log.last_run(), log.last_run(ok=True)
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today = log.since(midnight.isoformat(timespec="seconds"))
    week = log.since((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds"))
    cmp = log.last_compare()
    compared = {t["name"]: t["match"] for t in cmp["detail"]} if cmp else {}
    changed = (last_ok or {}).get("detail") or {}
    names = sorted(set(main_counts or {}) | set(copy_counts or {}), key=lambda n: (list(AREAS).index(_AREA_OF[n]) if n in _AREA_OF else 99, n))
    tables = [{"name": n, "area": _AREA_OF.get(n, "System"),
               "main_rows": (main_counts or {}).get(n), "copy_rows": (copy_counts or {}).get(n),
               "last_change": changed.get(n, [None, 0, 0, 0])[1:], "compared_match": compared.get(n)} for n in names]
    matching = sum(1 for t in tables if t["main_rows"] is not None and t["main_rows"] == t["copy_rows"])
    return {
        **fo.status(),
        "main": main, "copy": copy,
        "kpis": {
            "last_sync": last and {k: last[k] for k in ("at", "direction", "trigger", "ok", "error", "duration_ms")},
            "in_sync": {"rows": main["rows"], "tables": len(tables), "matching": matching},
            "today": today,
            "health_7d": {**week, "rate": (week["syncs"] - week["failed"]) / week["syncs"] if week["syncs"] else None},
            "pending": syncer.pending,
        },
        "tables": tables,
        "last_compare": cmp and {k: cmp[k] for k in ("at", "ok", "differs", "pending")},
        "abnormalities": abnormalities(fo, log, main_counts, copy_counts, syncer, last, last_ok, week),
    }


def history(fo, days=14):
    log = fo.log
    return {"days": log.daily(days), "runs": [{k: v for k, v in r.items() if k != "detail"} for r in log.recent_runs(50)],
            "switches": log.recent_switches(20), "keep_days": 90}


def compare(fo):
    """Check every table in both databases, row by row (count + checksum). Waits for a copy in progress first,
    so it never compares a half-written copy."""
    syncer = _syncer(fo)
    main_eng, copy_eng, temp = _engines(fo)
    if fo.read_only():
        raise RuntimeError("PostgreSQL can't be reached, so there is nothing to compare the copy with.")
    if copy_eng is None:
        raise RuntimeError("There is no copy yet to compare with.")
    with syncer._run_lock:
        pending = syncer.pending
        try:
            m1, m2 = MetaData(), MetaData()
            m1.reflect(bind=main_eng)
            m2.reflect(bind=copy_eng)
            out = []
            with main_eng.connect() as a, copy_eng.connect() as b:
                for name in sorted(n for n in m1.tables if n not in SKIP):
                    t1 = m1.tables[name]
                    cols = [c.name for c in t1.columns]
                    d1 = table_digest(a, t1, cols)
                    t2 = m2.tables.get(name)
                    d2 = table_digest(b, t2, cols) if t2 is not None and all(c in t2.c for c in cols) else (None, None)
                    out.append({"name": name, "area": _AREA_OF.get(name, "System"), "main_rows": d1[0],
                                "copy_rows": d2[0], "match": d1 == d2})
        finally:
            if temp:
                copy_eng.dispose()
    ok = all(t["match"] for t in out)
    fo.log.record_compare(ok, pending, out)
    return {"at": fo.log.last_compare()["at"], "ok": ok, "pending": pending, "differs": sum(not t["match"] for t in out),
            "tables": out}
