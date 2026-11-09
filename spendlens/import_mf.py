"""Load the extracted factsheet JSON (<folder>/_extracted/YYYY-MM/*.json, written by the mf-factsheet-analyst agent)
into the MF Analysis tables.

    python spendlens/import_mf.py fund_fact_sheet
    python spendlens/import_mf.py fund_fact_sheet --email me@x.com
    python spendlens/import_mf.py fund_fact_sheet --delete-imported

Morningstar fund reports (morningstarreport*.pdf anywhere in the folder) are read directly (mf_parsers.parse_morningstar)
and stored in mf_reports, to cross-check the factsheets. --delete-imported then deletes every PDF / Excel in the folder
whose sha256 is recorded in the database (mf_sources / mf_reports), so a file not yet extracted is never deleted.

Every file is validated first (mf.validate); one bad file stops the import and nothing is saved. Re-running is safe:
a file replaces what it imported before. The database is prepared as app.py does at start-up, so stop the backend
first (the two would write the SQLite mirror at the same time) and start it again afterwards.
"""
import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mf  # noqa: E402


def backend_running(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delete_imported(session, folder, log=print):
    """Delete the source files whose sha256 the database holds (imported). Returns the deleted paths."""
    from db.models import MfReport, MfSource
    known = {r.sha256 for r in session.query(MfSource.sha256)} | {r.sha256 for r in session.query(MfReport.sha256)}
    known.discard("")
    gone, busy = [], []
    for f in sorted(Path(folder).rglob("*")):
        if f.is_file() and "_extracted" not in f.parts and f.suffix.lower() in (".pdf", ".xlsx", ".xls") \
                and sha256_of(f) in known:
            try:
                f.unlink()
                gone.append(f)
            except PermissionError:   # open in a viewer (Windows locks it): keep it, it's in the DB anyway
                busy.append(f)
    log(f"Deleted {len(gone)} imported files" + (": " + ", ".join(g.name for g in gone[:8]) + (" ..." if len(gone) > 8 else "") if gone else ""))
    if busy:
        log(f"Kept {len(busy)} imported files that another program has open (close it and run again): "
            + ", ".join(b.name for b in busy))
    return gone


def load_folder(session, folder, log=print):
    """Validate every extracted JSON under folder/_extracted, then import them all. Raises SystemExit on any error."""
    files = sorted((Path(folder) / "_extracted").glob("*/*.json"))
    if not files:
        raise SystemExit(f"No extracted files in {Path(folder) / '_extracted'}: run /mf-factsheets in Claude Code first")
    payloads, problems = [], []
    for f in files:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{f}: not valid JSON ({e})")
            continue
        errors, _ = mf.validate(p)
        if errors:
            problems.append(f"{f}: " + "; ".join(errors[:5]))
        elif p["month"] != f.parent.name:
            problems.append(f"{f}: month {p['month']} but the folder is {f.parent.name}")
        else:
            payloads.append((f, p))
    if problems:
        raise SystemExit("Nothing imported; fix these first:\n  " + "\n  ".join(problems))
    results = []
    for f in sorted(Path(folder).rglob("*.pdf")):
        if "_extracted" in f.parts or not f.name.lower().startswith("morningstar"):
            continue
        import mf_parsers
        rep = mf_parsers.parse_morningstar(str(f))
        key = mf.import_report(session, rep, f.name, sha256_of(f), f.read_bytes())
        log(f"{rep.get('portfolio_date', '')[:7]}  {f.name}: Morningstar report for {rep['fund']} ({key})")
    # factsheets before portfolio disclosures, month by month: the disclosure's full holdings are applied last
    payloads.sort(key=lambda fp: (fp[1]["month"], fp[1].get("kind", "factsheet") == "portfolio", str(fp[0]).lower()))
    for f, p in payloads:
        r = mf.import_payload(session, p)
        results.append(r)
        log(f"{p['month']}  {p['source']}: {r['funds']} funds" + (f"  ({len(r['warnings'])} warnings)" if r["warnings"] else ""))
    session.commit()
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--email", help="the SpendLens user who owns the data (default: the first admin)")
    ap.add_argument("--delete-imported", action="store_true",
                    help="after importing, delete the source PDF / Excel files the database now holds")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    args = ap.parse_args(argv)
    if backend_running(args.port):
        raise SystemExit(f"The backend is running on port {args.port}. Stop it first, then run this again.")

    import envlocal
    envlocal.load()
    from db import failover
    from db.engine import SessionLocal
    from db.models import User

    failover.startup()
    try:
        with SessionLocal() as s:
            q = s.query(User).filter(User.email == args.email.strip().lower()) if args.email else \
                s.query(User).filter(User.role == "admin").order_by(User.id)
            user = q.first()
            if user is None:
                raise SystemExit(f"No user {args.email}" if args.email else "No admin user yet: start the app once first")
            uid, email = user.id, user.email
        print(f"Importing for {email}")
        with SessionLocal() as s:
            s.info["user_id"] = uid
            res = load_folder(s, args.folder)
            a = mf.analysis(s)
            if args.delete_imported:
                delete_imported(s, args.folder)
        held = sum(1 for f in a["funds"] if f["held"])
        print(f"Imported {len(res)} files. {len(a['funds'])} funds, {held} matched to your holdings, "
              f"{len(a['anomalies'])} anomalies, latest month {a['latest_month']}.")
        for u in a["unmatched_holdings"]:
            print(f"  not in any factsheet yet: {u['name']}")
    finally:
        failover.shutdown()


if __name__ == "__main__":
    main()
