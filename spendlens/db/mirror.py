"""Keeps a SQLite copy of the PostgreSQL primary, for db/failover.py to fall back on.

Each refresh builds a brand-new SQLite file (the current Alembic schema, from a template built once per
process), copies every table into it from PostgreSQL with db/replicate.py, verifies it, and only then swaps it
in with os.replace, so the mirror on disk is always a complete, verified copy. Refreshes run on a background
thread: ~10 s after the last commit (commits during that wait push it back), every 15 minutes regardless, and
once more at shutdown. The first refresh keeps the file that was there before (the app's old SQLite database)
as `<name>.pre-postgres.bak`. The time and outcome of the last refresh live in `<mirror>.mirror.json`.
"""
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import create_engine

from . import replicate

log = logging.getLogger("spendlens.mirror")


class Mirror:
    def __init__(self, primary, path, debounce=10.0, period=900.0, build_schema=replicate.build_schema):
        self.primary = primary
        self.path = os.path.abspath(path)
        self.meta_path = self.path + ".mirror.json"
        self.backup_path = os.path.splitext(self.path)[0] + ".pre-postgres.bak"
        self.debounce, self.period = debounce, period
        self._build_schema = build_schema
        self._template = None
        self._dirty_at = None
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self.paused = lambda: False      # set by failover: no refresh while PostgreSQL is down
        self.before_replace = lambda: None  # set by failover: close its read-only handles on the mirror
        self.runs = 0

    # ---- state -------------------------------------------------------------------------------------------
    def _read_meta(self):
        try:
            with open(self.meta_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _write_meta(self, **changes):
        meta = {**self._read_meta(), **changes}
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        os.replace(tmp, self.meta_path)

    def status(self):
        meta = self._read_meta()
        return {"path_name": os.path.basename(self.path), "updated_at": meta.get("updated_at"),
                "last_error": meta.get("last_error")}

    def exists(self):
        return os.path.isfile(self.path) and os.path.getsize(self.path) > 0

    # ---- scheduling --------------------------------------------------------------------------------------
    def mark_dirty(self, *_):
        with self._lock:
            self._dirty_at = time.monotonic()
        self._wake.set()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="sqlite-mirror")
            self._thread.start()

    def _loop(self):
        last_periodic = time.monotonic()
        while not self._stop.is_set():
            with self._lock:
                dirty_at = self._dirty_at
            now = time.monotonic()
            wait = last_periodic + self.period - now
            if dirty_at is not None:
                wait = min(wait, dirty_at + self.debounce - now)
            if wait > 0:
                self._wake.wait(wait)
                self._wake.clear()
                continue  # re-evaluate: a new commit may have pushed the deadline back
            if self._stop.is_set():
                break
            with self._lock:
                self._dirty_at = None
            last_periodic = time.monotonic()
            if not self.paused():
                self.run()

    def stop(self, final=True):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if final and not self.paused():
            self.run()
        if self._template and os.path.exists(self._template):
            try:
                os.remove(self._template)
            except OSError:
                pass

    # ---- one refresh -------------------------------------------------------------------------------------
    def _template_file(self):
        if not (self._template and os.path.exists(self._template)):
            folder, name = os.path.split(self.path)
            tpl = os.path.join(folder, f".{name}.template.db")  # rebuilt once per process start
            if os.path.exists(tpl):
                os.remove(tpl)
            self._build_schema(f"sqlite:///{tpl}", tpl)
            self._template = tpl
        return self._template

    def _sqlite_engine(self, path):
        return create_engine(f"sqlite:///{path}")

    def _backup_once(self):
        """Keep the file that was there before the first mirror (the old SQLite database), WAL included."""
        if not self.exists() or os.path.exists(self.backup_path) or self._read_meta().get("updated_at"):
            return  # nothing there, already kept, or what is there is an earlier mirror
        eng = self._sqlite_engine(self.path)
        try:
            with eng.connect() as c:
                c.exec_driver_sql("VACUUM INTO '" + self.backup_path.replace("'", "''") + "'")
        finally:
            eng.dispose()
        log.info("kept the previous SQLite database as %s", os.path.basename(self.backup_path))

    _swap = staticmethod(os.replace)  # Windows refuses while another process has the file open

    def _replace(self, fresh):
        self.before_replace()
        if self.exists():  # fold any WAL into the old file so its -wal/-shm can go; refuses if another program has it
            eng = self._sqlite_engine(self.path)
            try:
                with eng.connect() as c:
                    c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                eng.dispose()
        for side in (self.path + "-wal", self.path + "-shm"):
            if os.path.exists(side):
                try:
                    os.remove(side)
                except OSError as e:
                    raise RuntimeError(f"{os.path.basename(self.path)} is open in another program") from e
        for attempt in range(10):
            try:
                self._swap(fresh, self.path)
                return
            except PermissionError:
                if attempt == 9:
                    raise RuntimeError(f"{os.path.basename(self.path)} is locked by another program")
                time.sleep(0.3)

    def run(self):
        """Refresh the mirror now. Returns True on success. Never raises: a failure is logged and recorded."""
        if not self._run_lock.acquire(blocking=False):
            self.mark_dirty()  # one is already running; go again after it
            return False
        fresh = f"{self.path}.tmp-{os.getpid()}"
        try:
            shutil.copyfile(self._template_file(), fresh)
            tgt = self._sqlite_engine(fresh)
            try:
                _, mismatches = replicate.copy_all(self.primary, tgt)
            finally:
                tgt.dispose()
            if mismatches:
                raise RuntimeError("copy did not verify: " + ", ".join(m[0] for m in mismatches))
            self._backup_once()
            self._replace(fresh)
            self.runs += 1
            self._write_meta(updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), last_error=None)
            return True
        except Exception as e:  # keep the old mirror; the next trigger tries again
            log.warning("SQLite mirror refresh failed: %s", e)
            try:
                self._write_meta(last_error=str(e)[:300])
            except OSError:
                pass
            return False
        finally:
            if os.path.exists(fresh):
                try:
                    os.remove(fresh)
                except OSError:
                    pass
            self._run_lock.release()
