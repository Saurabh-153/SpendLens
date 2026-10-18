"""PostgreSQL as the primary, the SQLite mirror (db/mirror.py) as a read-only fallback.

Only active when DATABASE_URL points at PostgreSQL; with SQLite as the primary none of this runs and the app
behaves exactly as before. At startup an unreachable PostgreSQL (3 s timeout) with a mirror on disk starts the
app in 'read-only-fallback' on the mirror, opened read-only and without running migrations. While running, a
health check every 30 s (and any lost-connection error during a request) moves sessions between the two:
SessionLocal is re-bound to the mirror on failure and back to PostgreSQL on recovery, followed by a fresh mirror.
In fallback every write request under /spendlens/api is refused with 503, and the writes that normally happen
behind the scenes (due SIPs, snapshots, price refreshes) are skipped: see `read_only()` at those call sites.
"""
import logging
import os
import threading
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


class Failover:
    def __init__(self, primary, sessions, mirror, check_every=30.0, migrate=None):
        self.primary = primary
        self.sessions = sessions
        self.mirror = mirror
        self.check_every = check_every
        self.migrate = migrate  # runs Alembic on the primary when it comes back after a fallback start
        self.mode = NORMAL
        self.needs_migration = False
        self._ro_engine = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        mirror.paused = self.read_only
        mirror.before_replace = self._close_mirror_engine

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

    def enter_fallback(self, reason):
        with self._lock:
            if self.mode == FALLBACK:
                return True
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
        self.mirror.mark_dirty()

    def check(self):
        ok = self.primary_ok()
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

    def start(self):
        def loop():
            while not self._stop.wait(self.check_every):
                self.check()
        if self._thread is None:
            self._thread = threading.Thread(target=loop, daemon=True, name="failover-health")
            self._thread.start()

    def stop(self):
        self._stop.set()

    def status(self):
        return {"primary": "postgresql", "mode": self.mode, "mirror": self.mirror.status()}

    def read_only_message(self):
        when = self.mirror.status().get("updated_at")
        try:
            when = datetime.fromisoformat(when).astimezone().strftime("%d %b %Y, %H:%M") if when else None
        except ValueError:
            pass
        return ("The main database (PostgreSQL) is unavailable. Showing a read-only copy from "
                f"{when or 'an unknown time'}; changes are disabled until it is back.")


_instance = None


def read_only():
    return bool(_instance and _instance.read_only())


def status():
    if _instance is None:
        return {"primary": "sqlite", "mode": NORMAL, "mirror": None}
    return _instance.status()


def mirror_path(default_sqlite_path):
    return os.path.abspath(os.environ.get("SPENDLENS_MIRROR") or default_sqlite_path)


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
    fo = Failover(eng.engine, eng.SessionLocal, mirror, migrate=prepare_database)
    if fo.primary_ok():
        prepare_database()
        mirror.mark_dirty()  # a fresh mirror shortly after start-up
    elif mirror.exists():
        fo.needs_migration = True
        fo.enter_fallback("unreachable at start-up")
    else:
        url = eng.engine.url
        raise RuntimeError(f"PostgreSQL at {url.host}:{url.port} is unreachable and there is no SQLite mirror at "
                           f"{mirror.path} to fall back to. Start PostgreSQL, or remove DATABASE_URL to use SQLite.")
    event.listen(eng.SessionLocal, "after_commit", lambda s: None if fo.read_only() else mirror.mark_dirty())
    mirror.start()
    fo.start()
    _instance = fo
    return fo


def shutdown():
    if _instance is not None:
        _instance.stop()
        _instance.mirror.stop(final=True)


def install(app):
    """Read-only guard, lost-connection detection and the shutdown mirror, for the FastAPI app."""
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def database_guard(request, call_next):
        fo = _instance
        api = request.url.path.startswith("/spendlens/api")
        if fo and api and fo.read_only() and request.method not in _WRITE_METHODS_OK:
            return JSONResponse(status_code=503, content={"detail": fo.read_only_message()})
        try:
            return await call_next(request)
        except DBAPIError as e:
            if fo is None or not api:
                raise
            if fo.read_only():
                return JSONResponse(status_code=503, content={"detail": fo.read_only_message()})
            if getattr(e, "connection_invalidated", False) or e.__class__.__name__ in ("OperationalError", "InterfaceError"):
                fo.signal_failure()
                return JSONResponse(status_code=503, content={
                    "detail": "Lost the connection to the main database (PostgreSQL). Switching to the read-only "
                              "copy; try again in a moment."})
            raise

    app.on_event("shutdown")(shutdown)
