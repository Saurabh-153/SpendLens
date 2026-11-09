"""Which database is the main one, the copy kept in the other, and the read-only fallback.

Only active when DATABASE_URL points at PostgreSQL; without it the app runs on SQLite exactly as before and none
of this runs. With it, one of the two is the main database (the one that takes saves) and the other is kept as a
copy of it: PostgreSQL -> the SQLite file (db/mirror.Mirror), or, after a switch from the UI (`switch()`), the
SQLite file -> PostgreSQL (db/mirror.PostgresSync). A switch pauses the API for a few seconds, copies the current
main database into the other and verifies it, then swaps their roles; the choice is kept in database-mode.json
next to the SQLite file, so a restart keeps it.

With PostgreSQL as the main database, an unreachable PostgreSQL (3 s timeout) at start-up, on the 30 s health
check or on a lost connection during a request moves the app onto the SQLite copy, read-only: every write request
under /spendlens/api gets 503 and the writes that normally happen behind the scenes (due SIPs, snapshots, price
refreshes) are skipped (see `read_only()` at those call sites). When PostgreSQL answers again the app moves back.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import Delete, Insert, Update, create_engine, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

log = logging.getLogger("spendlens.failover")

NORMAL = "normal"
FALLBACK = "read-only-fallback"
_WRITE_METHODS_OK = {"GET", "HEAD", "OPTIONS"}


class _Skipped:
    """Stands in for the result of a write statement that was not run."""
    rowcount = 0

    def scalar(self):
        return None

    first = one_or_none = scalar_one_or_none = scalar

    def all(self):
        return []

    fetchall = all

    def scalars(self):
        return self

    def __iter__(self):
        return iter(())


def _is_write(statement):
    if isinstance(statement, (Insert, Update, Delete)):
        return True
    if isinstance(statement, TextClause):
        words = statement.text.lstrip().split(None, 1)
        return bool(words) and words[0].upper() in ("INSERT", "UPDATE", "DELETE", "REPLACE")
    return False


class ReadOnlySession(Session):
    """Session class used while on the mirror: anything a read path still tries to save is dropped, not raised."""

    def flush(self, objects=None):
        pass

    def commit(self):
        self.rollback()

    def execute(self, statement, *args, **kwargs):
        if _is_write(statement):
            return _Skipped()
        return super().execute(statement, *args, **kwargs)


class SwitchError(Exception):
    """A switch that could not be done; the message says why, for the user."""


class Failover:
    def __init__(self, primary, sessions, mirror, check_every=30.0, migrate=None, prepare_sqlite=None, log=None):
        self.primary = primary            # the PostgreSQL engine, whichever role it has right now
        self.sessions = sessions
        self.mirror = mirror              # PostgreSQL -> SQLite file, while PostgreSQL is the main database
        self.pg_sync = None               # SQLite file -> PostgreSQL, while SQLite is the main database
        self.check_every = check_every
        self.migrate = migrate            # runs Alembic on PostgreSQL (after a start without it)
        self.prepare_sqlite = prepare_sqlite or (lambda path: None)  # brings the SQLite file to the current schema
        self.kind = "postgresql"          # which database is the main one
        self.mode = NORMAL
        self.needs_migration = False
        self.switching = False
        self.active = 0                   # requests in flight, kept by the middleware
        self.mode_file = os.path.join(os.path.dirname(mirror.path), "database-mode.json")
        self._ro_engine = None
        self._rw_engine = None
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        mirror.paused = lambda: self.read_only() or self.kind != "postgresql"
        mirror.before_replace = self._close_mirror_engine
        if log is None:
            from db.synclog import SyncLog
            log = SyncLog(os.path.join(os.path.dirname(mirror.path), "spendlens_ops.db"))
        self.log = log                    # every copy, switch and comparison (db/synclog.py)
        self._switch_totals = {}
        mirror.log = log
        self.last_save_at = None

    def read_only(self):
        return self.mode == FALLBACK

    def primary_ok(self):
        try:
            with self.primary.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _mirror_engine(self):
        if self._ro_engine is None:
            uri = Path(self.mirror.path).as_uri()  # file:///C:/... with spaces escaped
            self._ro_engine = create_engine(f"sqlite:///{uri}?mode=ro&uri=true", connect_args={"check_same_thread": False})
        return self._ro_engine

    def _close_mirror_engine(self):
        if self._ro_engine is not None:
            self._ro_engine.dispose()

    def _sqlite_main_engine(self):
        if self._rw_engine is None:
            self._rw_engine = create_engine(f"sqlite:///{self.mirror.path}", connect_args={"check_same_thread": False})
        return self._rw_engine

    def _sync_to_postgres(self):
        if self.pg_sync is None:
            from db.mirror import PostgresSync
            self.pg_sync = PostgresSync(self._sqlite_main_engine(), self.primary, self.mirror.path,
                                        debounce=self.mirror.debounce, period=self.mirror.period)
            self.pg_sync.paused = lambda: self.kind != "sqlite"
            self.pg_sync.log = self.log
        return self.pg_sync

    # ---- read-only fallback (PostgreSQL is the main database but can't be reached) ----------------------
    def enter_fallback(self, reason):
        with self._lock:
            if self.mode == FALLBACK or self.kind != "postgresql":
                return self.mode == FALLBACK
            if not self.mirror.exists():
                log.error("PostgreSQL is unavailable (%s) and there is no SQLite mirror to fall back to", reason)
                return False
            self.sessions.configure(bind=self._mirror_engine())
            self.sessions.class_ = ReadOnlySession
            self.mode = FALLBACK
            log.warning("PostgreSQL is unavailable (%s): serving the read-only SQLite mirror", reason)
            return True

    def leave_fallback(self):
        with self._lock:
            if self.mode == NORMAL:
                return
            if self.needs_migration and self.migrate:
                self.migrate()
                self.needs_migration = False
            self.sessions.configure(bind=self.primary)
            self.sessions.class_ = Session
            self.mode = NORMAL
            self._close_mirror_engine()
            self._ro_engine = None
            log.warning("PostgreSQL is back: writes are enabled again")
        self.mirror.mark_dirty("recovery")

    def check(self):
        ok = self.primary_ok()
        if self.kind != "postgresql":
            if ok and self.pg_sync and self.pg_sync.status().get("last_error"):
                self.pg_sync.mark_dirty("recovery")  # PostgreSQL is back after a failed copy: copy again soon
            return ok
        if ok and self.mode == FALLBACK:
            try:
                self.leave_fallback()
            except Exception as e:  # e.g. migrations failed: stay read-only, try again next time
                log.warning("PostgreSQL answered but could not be switched back to: %s", e)
        elif not ok and self.mode == NORMAL:
            self.enter_fallback("health check failed")
        return ok

    def signal_failure(self):
        threading.Thread(target=self.check, daemon=True, name="failover-check").start()

    # ---- switching the main database --------------------------------------------------------------------
    def _wait_idle(self, timeout=10.0):
        """Let requests already running finish (the switch request itself counts as one)."""
        end = time.monotonic() + timeout
        while self.active > 1 and time.monotonic() < end:
            time.sleep(0.05)

    def _use_sqlite(self):
        self._close_mirror_engine()
        self._ro_engine = None
        self.sessions.configure(bind=self._sqlite_main_engine())
        self.sessions.class_ = Session
        self.kind, self.mode = "sqlite", NORMAL
        self._sync_to_postgres().start()

    def _use_postgres(self):
        self.sessions.configure(bind=self.primary)
        self.sessions.class_ = Session
        if self.pg_sync is not None:
            self.pg_sync.stop(final=False)
            self.pg_sync = None
        if self._rw_engine is not None:
            self._rw_engine.dispose()
            self._rw_engine = None
        self.kind, self.mode = "postgresql", NORMAL

    def switch(self, to):
        """Make `to` ('sqlite' or 'postgresql') the main database, copying everything into it first."""
        if to not in ("sqlite", "postgresql"):
            raise ValueError("choose 'sqlite' or 'postgresql'")
        if not self._switch_lock.acquire(blocking=False):
            raise SwitchError("A switch is already running.")
        try:
            if to == self.kind:
                return self.status()
            frm, started = self.kind, time.monotonic()
            self.switching = True
            try:
                self._wait_idle()
                self._switch_to(to)
            except SwitchError as e:
                self.log.record_switch(frm, to, False, (time.monotonic() - started) * 1000, error=str(e))
                raise
            totals = self._switch_totals
            self.log.record_switch(frm, to, True, (time.monotonic() - started) * 1000,
                                   rows_total=sum(totals.values()) if totals else None, tables_total=len(totals) or None)
            log.warning("main database switched to %s", self.kind)
            return self.status()
        finally:
            self.switching = False
            self._switch_lock.release()

    def _switch_to(self, to):
        """The copy and the re-binding for switch(); raises SwitchError, leaving things as they were."""
        with self._lock:
            if to == "sqlite":
                if self.mode == NORMAL:
                    if not self.mirror.run(wait=True, trigger="switch"):  # a fresh, verified copy of PostgreSQL
                        raise SwitchError("Could not copy PostgreSQL into SQLite: "
                                          f"{self.mirror.status().get('last_error') or 'unknown error'}")
                elif not self.mirror.exists():
                    raise SwitchError("There is no SQLite copy to switch to.")
                self._close_mirror_engine()
                self._ro_engine = None
                self.prepare_sqlite(self.mirror.path)
                self._switch_totals = self.mirror.last_totals
                self._use_sqlite()
            else:
                if not self.primary_ok():
                    raise SwitchError("PostgreSQL can't be reached, so it can't take over. Start it and try again.")
                if self.needs_migration and self.migrate:
                    self.migrate()
                    self.needs_migration = False
                if not self._sync_to_postgres().run(wait=True, trigger="switch"):  # everything saved in SQLite, into PostgreSQL
                    raise SwitchError("Could not copy SQLite into PostgreSQL: "
                                      f"{self.pg_sync.status().get('last_error') or 'unknown error'}")
                self._switch_totals = self.pg_sync.last_totals
                self._use_postgres()
            self._save_mode()

    def _save_mode(self):
        tmp = self.mode_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"primary": self.kind}, f)
        os.replace(tmp, self.mode_file)

    def saved_mode(self):
        try:
            with open(self.mode_file, encoding="utf-8") as f:
                return json.load(f).get("primary")
        except (OSError, ValueError):
            return None

    # ---- lifecycle and status ---------------------------------------------------------------------------
    def start(self):
        def loop():
            while not self._stop.wait(self.check_every):
                self.check()
        if self._thread is None:
            self._thread = threading.Thread(target=loop, daemon=True, name="failover-health")
            self._thread.start()

    def stop(self):
        self._stop.set()

    def on_commit(self, *_):
        self.last_save_at = datetime.now().astimezone().isoformat(timespec="seconds")
        if self.kind == "sqlite":
            self._sync_to_postgres().mark_dirty("save")
        elif not self.read_only():
            self.mirror.mark_dirty("save")

    def status(self):
        on_pg = self.kind == "postgresql"
        copy = self.mirror.status() if on_pg else self._sync_to_postgres().status()
        return {"primary": self.kind, "mode": self.mode, "switching": self.switching, "can_switch": True,
                "mirror": self.mirror.status() if on_pg else None,
                "copy": {"to": "sqlite" if on_pg else "postgresql",
                         "updated_at": copy.get("updated_at"), "last_error": copy.get("last_error")}}

    def read_only_message(self):
        when = self.mirror.status().get("updated_at")
        try:
            when = datetime.fromisoformat(when).astimezone().strftime("%d %b %Y, %H:%M") if when else None
        except ValueError:
            pass
        return ("The main database (PostgreSQL) is unavailable. Showing a read-only copy from "
                f"{when or 'an unknown time'}; changes are disabled until it is back. To keep working, switch to "
                "SQLite in Settings › Database.")


_instance = None


def read_only():
    return bool(_instance and _instance.read_only())


def status():
    if _instance is None:
        return {"primary": "sqlite", "mode": NORMAL, "switching": False, "can_switch": False, "mirror": None, "copy": None}
    return _instance.status()


def switch(to):
    if _instance is None:
        raise SwitchError("PostgreSQL isn't configured (no DATABASE_URL in .env.local), so there is nothing to switch to.")
    return _instance.switch(to)


def mirror_path(default_sqlite_path):
    return os.path.abspath(os.environ.get("SPENDLENS_MIRROR") or default_sqlite_path)


def _prepare_sqlite_file(path):
    from db.replicate import build_schema
    build_schema(f"sqlite:///{path}", path)


def startup():
    """Called once by app.py instead of prepare_database()."""
    global _instance
    from db import engine as eng
    from db.migrate import prepare_database
    from db.mirror import Mirror

    if not eng.IS_POSTGRES:
        prepare_database()
        return None
    mirror = Mirror(eng.engine, mirror_path(eng._DEFAULT_SQLITE_PATH))
    fo = Failover(eng.engine, eng.SessionLocal, mirror, migrate=prepare_database, prepare_sqlite=_prepare_sqlite_file)
    pg_up = fo.primary_ok()
    if fo.saved_mode() == "sqlite" and mirror.exists():
        _prepare_sqlite_file(mirror.path)
        if pg_up:
            prepare_database()
        else:
            fo.needs_migration = True
        fo._use_sqlite()
        fo.pg_sync.mark_dirty("startup")
    elif pg_up:
        prepare_database()
        mirror.mark_dirty("startup")  # a fresh mirror shortly after start-up
    elif mirror.exists():
        fo.needs_migration = True
        fo.enter_fallback("unreachable at start-up")
    else:
        url = eng.engine.url
        raise RuntimeError(f"PostgreSQL at {url.host}:{url.port} is unreachable and there is no SQLite mirror at "
                           f"{mirror.path} to fall back to. Start PostgreSQL, or remove DATABASE_URL to use SQLite.")
    if not event.contains(Session, "after_commit", _after_commit):
        event.listen(Session, "after_commit", _after_commit)
    mirror.start()
    fo.start()
    _instance = fo
    return fo


def _after_commit(session):
    """Every committed save schedules a copy. Listens on the base Session class: SessionLocal's own class is swapped
    for the read-only fallback and back, and a listener on it would be dropped with the swapped-out class."""
    if _instance is not None:
        _instance.on_commit()


def shutdown():
    if _instance is not None:
        _instance.stop()
        _instance.mirror.stop(final=True)
        if _instance.pg_sync is not None:
            _instance.pg_sync.stop(final=True)


_ALWAYS_ALLOWED = ("/spendlens/api/status", "/spendlens/api/database/switch",
                   "/spendlens/api/database/overview", "/spendlens/api/database/history")


def install(app):
    """Read-only guard, the pause during a switch, lost-connection detection and the shutdown copy."""
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def database_guard(request, call_next):
        fo = _instance
        path = request.url.path
        api = path.startswith("/spendlens/api")
        if fo and api and path not in _ALWAYS_ALLOWED:
            if fo.switching:
                return JSONResponse(status_code=503, content={
                    "detail": "Switching the main database; try again in a few seconds."})
            if fo.read_only() and request.method not in _WRITE_METHODS_OK:
                return JSONResponse(status_code=503, content={"detail": fo.read_only_message()})
        if fo:
            fo.active += 1
        try:
            return await call_next(request)
        except DBAPIError as e:
            if fo is None or not api or fo.kind != "postgresql":
                raise
            if fo.read_only():
                return JSONResponse(status_code=503, content={"detail": fo.read_only_message()})
            if getattr(e, "connection_invalidated", False) or e.__class__.__name__ in ("OperationalError", "InterfaceError"):
                fo.signal_failure()
                return JSONResponse(status_code=503, content={
                    "detail": "Lost the connection to the main database (PostgreSQL). Switching to the read-only "
                              "copy; try again in a moment."})
            raise
        finally:
            if fo:
                fo.active -= 1

    app.on_event("shutdown")(shutdown)
