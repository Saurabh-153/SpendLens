"""The record of every copy between the two databases, every switch and every comparison (Settings › Database).

Kept in its own small SQLite file next to the database copy (`spendlens_ops.db`), never inside PostgreSQL or the
copy: those are overwritten by each sync, and a switch would otherwise mix the two histories. Rows older than
90 days are pruned on every write. Also keeps, per direction, the row index of the last copy (db/replicate.py's
row_index), so the next copy can say exactly how many rows were added, changed and removed, across restarts too.
"""
import json
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, delete, func, insert, select

KEEP_DAYS = 90

_meta = MetaData()
runs = Table(
    "sync_runs", _meta,
    Column("id", Integer, primary_key=True),
    Column("at", String, nullable=False),            # UTC ISO time the copy finished
    Column("direction", String, nullable=False),     # postgresql→sqlite / sqlite→postgresql
    Column("trigger", String, nullable=False),       # save / periodic / startup / shutdown / switch / recovery / manual
    Column("ok", Integer, nullable=False),
    Column("error", Text),
    Column("duration_ms", Integer),
    Column("rows_total", Integer),
    Column("tables_total", Integer),
    Column("rows_added", Integer),
    Column("rows_changed", Integer),
    Column("rows_removed", Integer),
    Column("tables_changed", Integer),
    Column("detail", Text),                          # JSON {table: [rows, added, changed, removed]}
)
switches = Table(
    "sync_switches", _meta,
    Column("id", Integer, primary_key=True),
    Column("at", String, nullable=False),
    Column("from_kind", String), Column("to_kind", String),
    Column("ok", Integer, nullable=False), Column("error", Text),
    Column("rows_total", Integer), Column("tables_total", Integer), Column("pause_ms", Integer),
)
compares = Table(
    "sync_compares", _meta,
    Column("id", Integer, primary_key=True),
    Column("at", String, nullable=False),
    Column("ok", Integer, nullable=False),
    Column("pending", Integer),                      # saves not yet copied when it ran: differences then are expected
    Column("differs", Integer),
    Column("detail", Text),                          # JSON [{name, main_rows, copy_rows, match}]
)
snapshots = Table(
    "sync_snapshots", _meta,
    Column("direction", String, primary_key=True),
    Column("at", String), Column("data", Text),
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SyncLog:
    def __init__(self, path):
        self.path = str(path)
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False})
        _meta.create_all(self.engine)
        self._lock = threading.Lock()

    def _prune(self, c):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
        for t in (runs, switches, compares):
            c.execute(delete(t).where(t.c.at < cutoff))

    # ---- writes -------------------------------------------------------------------------------------------
    def record_run(self, direction, trigger, ok, duration_ms, error=None, totals=None, changes=None):
        """totals: {table: rows}; changes: {table: (added, changed, removed)} from replicate.diff_snapshots, or None
        for the very first copy, which is the starting point everything later is compared with."""
        baseline = ok and changes is None
        totals, changes = totals or {}, changes or {}
        detail = {name: [rows, *changes.get(name, (0, 0, 0))] for name, rows in totals.items()}
        row = {"at": now_iso(), "direction": direction, "trigger": trigger, "ok": int(bool(ok)), "error": error,
               "duration_ms": int(duration_ms), "rows_total": sum(totals.values()) if ok else None,
               "tables_total": len(totals) if ok else None,
               "rows_added": sum(c[0] for c in changes.values()), "rows_changed": sum(c[1] for c in changes.values()),
               "rows_removed": sum(c[2] for c in changes.values()), "tables_changed": None if baseline else len(changes),
               "detail": json.dumps(detail) if ok else None}
        with self._lock, self.engine.begin() as c:
            c.execute(insert(runs).values(**row))
            self._prune(c)

    def record_switch(self, from_kind, to_kind, ok, pause_ms, error=None, rows_total=None, tables_total=None):
        with self._lock, self.engine.begin() as c:
            c.execute(insert(switches).values(at=now_iso(), from_kind=from_kind, to_kind=to_kind, ok=int(bool(ok)),
                                              error=error, rows_total=rows_total, tables_total=tables_total,
                                              pause_ms=int(pause_ms)))
            self._prune(c)

    def record_compare(self, ok, pending, tables):
        with self._lock, self.engine.begin() as c:
            c.execute(insert(compares).values(at=now_iso(), ok=int(bool(ok)), pending=pending,
                                              differs=sum(1 for t in tables if not t["match"]), detail=json.dumps(tables)))
            self._prune(c)

    def save_snapshot(self, direction, data):
        with self._lock, self.engine.begin() as c:
            c.execute(delete(snapshots).where(snapshots.c.direction == direction))
            c.execute(insert(snapshots).values(direction=direction, at=now_iso(), data=json.dumps(data)))

    def last_snapshot(self, direction):
        with self.engine.connect() as c:
            r = c.execute(select(snapshots.c.data).where(snapshots.c.direction == direction)).first()
        return json.loads(r[0]) if r else None

    # ---- reads --------------------------------------------------------------------------------------------
    @staticmethod
    def _run_out(r):
        d = dict(r._mapping)
        d["ok"] = bool(d["ok"])
        d["detail"] = json.loads(d["detail"]) if d.get("detail") else None
        return d

    def recent_runs(self, limit=50):
        with self.engine.connect() as c:
            rows = c.execute(select(runs).order_by(runs.c.id.desc()).limit(limit)).all()
        return [self._run_out(r) for r in rows]

    def last_run(self, ok=None):
        q = select(runs).order_by(runs.c.id.desc()).limit(1)
        if ok is not None:
            q = q.where(runs.c.ok == int(ok))
        with self.engine.connect() as c:
            r = c.execute(q).first()
        return self._run_out(r) if r else None

    def consecutive_failures(self):
        n = 0
        for r in self.recent_runs(20):
            if r["ok"]:
                break
            n += 1
        return n

    def since(self, iso):
        """Totals of the runs finished at or after `iso`."""
        with self.engine.connect() as c:
            r = c.execute(select(func.count(), func.coalesce(func.sum(1 - runs.c.ok), 0),
                                 func.coalesce(func.sum(func.coalesce(runs.c.rows_added, 0) + func.coalesce(runs.c.rows_changed, 0)
                                                       + func.coalesce(runs.c.rows_removed, 0)), 0))
                          .where(runs.c.at >= iso)).first()
            tables = c.execute(select(runs.c.detail).where(runs.c.at >= iso, runs.c.ok == 1)).all()
        touched = set()
        for (detail,) in tables:
            for name, v in (json.loads(detail) if detail else {}).items():
                if any(v[1:]):
                    touched.add(name)
        return {"syncs": r[0], "failed": int(r[1]), "rows_changed": int(r[2]), "tables_changed": len(touched)}

    def daily(self, days=14, tz=None):
        """[{date, syncs, failed, rows_changed}] for the last `days` local days, oldest first, empty days included."""
        tz = tz or datetime.now().astimezone().tzinfo
        today = datetime.now(tz).date()
        start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tz).astimezone(timezone.utc)
        out = {(today - timedelta(days=i)).isoformat(): {"syncs": 0, "failed": 0, "rows_changed": 0} for i in range(days)}
        with self.engine.connect() as c:
            rows = c.execute(select(runs.c.at, runs.c.ok, runs.c.rows_added, runs.c.rows_changed, runs.c.rows_removed)
                             .where(runs.c.at >= start.isoformat(timespec="seconds"))).all()
        for at, ok, a, ch, rm in rows:
            day = datetime.fromisoformat(at).astimezone(tz).date().isoformat()
            if day in out:
                out[day]["syncs"] += 1
                out[day]["failed"] += 0 if ok else 1
                out[day]["rows_changed"] += (a or 0) + (ch or 0) + (rm or 0)
        return [{"date": d, **v} for d, v in sorted(out.items())]

    def recent_switches(self, limit=20):
        with self.engine.connect() as c:
            rows = c.execute(select(switches).order_by(switches.c.id.desc()).limit(limit)).all()
        return [{**dict(r._mapping), "ok": bool(r.ok)} for r in rows]

    def last_compare(self):
        with self.engine.connect() as c:
            r = c.execute(select(compares).order_by(compares.c.id.desc()).limit(1)).first()
        if not r:
            return None
        d = dict(r._mapping)
        return {**d, "ok": bool(d["ok"]), "detail": json.loads(d["detail"]) if d["detail"] else []}

