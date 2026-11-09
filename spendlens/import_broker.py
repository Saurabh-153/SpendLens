"""Import broker files from a folder into the stock ledger, then run the Yahoo refresh.

    python spendlens/import_broker.py tradebook                 # folder with one sub-folder per demat account
    python spendlens/import_broker.py tradebook --email me@x.com
    python spendlens/import_broker.py tradebook --no-refresh
    python spendlens/import_broker.py tradebook --events actions.json   # also add corporate actions (a JSON list)

Each sub-folder's name is the account label (tradebook/SK, tradebook/SS). Every .xlsx / .csv in it is recognised by its
contents: Console tradebooks, dividend statements (keep Console's file name, it carries the period) and the holdings
statement. Running it again is safe: trades already stored are skipped and a dividend statement replaces its period,
so new files can simply be added to the folder and the command re-run. Once imported, the files can be deleted.

The database is prepared exactly as app.py does at start-up (Alembic upgrade; on PostgreSQL the SQLite mirror, which is
copied again before exiting). Stop the running backend first so the two don't write the mirror at the same time.
"""
import argparse
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Only when run as a command: importing this module (tests do) must never point the process, or the subprocesses
    # it starts, at the real database in .env.local.
    import envlocal

    envlocal.load()

import dividend_agent  # noqa: E402
import equity as eq  # noqa: E402
import equity_import as imp  # noqa: E402
from db import failover  # noqa: E402
from db.engine import SessionLocal  # noqa: E402
from db.models import EquityAudit, EquityEvent, User  # noqa: E402

FILE_TYPES = (".xlsx", ".csv")


def backend_running(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def import_folder(session, folder, log=print):
    """Import every account sub-folder of `folder`; returns {account: [result]}."""
    folder = Path(folder)
    accounts = sorted(p for p in folder.iterdir() if p.is_dir())
    if not accounts:
        raise SystemExit(f"{folder} has no account sub-folders (e.g. {folder / 'SK'})")
    out = {}
    for d in accounts:
        files = [(f.name, f.read_bytes()) for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in FILE_TYPES]
        if not files:
            log(f"{d.name}: no .xlsx / .csv files, skipped")
            continue
        canon = eq.make_canonical(eq.all_events(session))
        results = imp.import_files(session, d.name, files, lambda raw, known: eq.dividend_symbol(raw, known, canon))
        out[d.name.upper()] = results
        for r in results:
            log(f"{d.name.upper()}  {r['kind']:<9} {r['file']}: {r['summary']}")
    return out


def add_events(session, items, log=print):
    """Add corporate actions ({kind, symbol, ex_date, account, qty, price, ...}); an identical one already stored is skipped."""
    from fastapi import HTTPException
    from routes.equity_routes import EventIn, _clean_event
    added = 0
    for raw in items:
        try:
            vals = _clean_event(EventIn(**raw))
        except HTTPException as e:
            raise SystemExit(f"Bad event {raw}: {e.detail}")
        same = session.query(EquityEvent).filter(*(getattr(EquityEvent, k) == v for k, v in vals.items() if k != "note")).first()
        if same:
            log(f"event {vals['kind']} {vals['symbol']} {vals['ex_date']}: already there")
            continue
        session.add(EquityEvent(source="manual", **vals))
        session.add(EquityAudit(kind="event", account=vals["account"], summary=f"Added {vals['kind']} {vals['symbol']} {vals['ex_date']}",
                                detail=json.dumps(vals)))
        added += 1
        log(f"event {vals['kind']} {vals['symbol']} {vals['ex_date']}: added")
    session.commit()
    return added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", help="folder with one sub-folder per demat account")
    ap.add_argument("--email", help="the SpendLens user who owns the data (default: the first admin)")
    ap.add_argument("--events", help="JSON file with a list of corporate actions to add")
    ap.add_argument("--no-refresh", action="store_true", help="skip the Yahoo refresh after importing")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)), help="backend port to check (default 5000)")
    args = ap.parse_args(argv)

    if not Path(args.folder).is_dir():
        raise SystemExit(f"No folder {args.folder}")
    if backend_running(args.port):
        raise SystemExit(f"The backend is running on port {args.port}. Stop it first, then run this again.")

    failover.startup()
    try:
        with SessionLocal() as s:
            q = s.query(User).filter(User.email == args.email.strip().lower()) if args.email else \
                s.query(User).filter(User.role == "admin").order_by(User.id)
            user = q.first()
            if user is None:
                raise SystemExit(f"No user {args.email}" if args.email else "No admin user yet: start the app once first")
            uid = user.id
        print(f"Importing for {user.email}")
        with SessionLocal() as s:
            s.info["user_id"] = uid   # rows are stamped with this user and every query is scoped to them
            try:
                import_folder(s, args.folder)
            except imp.ImportError_ as e:
                s.rollback()
                raise SystemExit(f"Import stopped, nothing saved: {e}")
            if args.events:
                add_events(s, json.loads(Path(args.events).read_text(encoding="utf-8")))
            if not args.no_refresh:
                print("Refreshing from Yahoo…")
                print(dividend_agent.refresh(s)["summary"])
            a = eq.audit(s)
            levels = {lvl: sum(1 for i in a["issues"] if i["level"] == lvl) for lvl in ("error", "warning", "info")}
            print(f"Audit: {levels['error']} errors, {levels['warning']} warnings, {levels['info']} info")
            for i in a["issues"]:
                if i["level"] == "error":
                    print(f"  {i.get('account', '')} {i['symbol']} {i.get('date', '')}: {i['message']}")
    finally:
        failover.shutdown()   # on PostgreSQL: the final copy to the SQLite mirror


if __name__ == "__main__":
    main()
