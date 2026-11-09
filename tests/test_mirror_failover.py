"""The SQLite mirror of the PostgreSQL primary and the read-only fallback onto it (db/replicate.py, db/mirror.py,
db/failover.py). Everything here runs on temp files, and on PostgreSQL only inside a throwaway schema."""
import os
import shutil
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from conftest import ADMIN_TOKEN, ON_POSTGRES, ROOT

UNREACHABLE = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nowhere"


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """An empty SQLite file with the current schema, copied for each test that needs one."""
    from db.replicate import build_schema
    path = tmp_path_factory.mktemp("tpl") / "template.db"
    build_schema(f"sqlite:///{path}", str(path))
    return path


def fresh_sqlite(template, folder, name="copy.db"):
    path = Path(folder) / name
    shutil.copyfile(template, path)
    return path


@pytest.fixture(scope="module")
def mirror_file(seeded_db, template, tmp_path_factory):
    """A complete copy of the seeded test database as a SQLite file: what a mirror refresh produces."""
    from db.engine import engine
    from db.replicate import copy_all
    path = fresh_sqlite(template, tmp_path_factory.mktemp("mirror"), "mirror.db")
    tgt = create_engine(f"sqlite:///{path}")
    _, bad = copy_all(engine, tgt)
    tgt.dispose()
    assert bad == []
    return path


def count(engine, table):
    with engine.connect() as c:
        return c.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()


# ---- replicate --------------------------------------------------------------------------------------------

def test_copy_into_sqlite_matches_every_table(seeded_db, template, tmp_path):
    """Primary (SQLite here, PostgreSQL in the Postgres run) -> a fresh SQLite file, verified by checksum."""
    from db.engine import engine
    from db.replicate import copy_all
    tgt = create_engine(f"sqlite:///{fresh_sqlite(template, tmp_path)}")
    tables, bad = copy_all(engine, tgt)
    assert bad == [] and len(tables) >= 30
    for t in ("categories", "subcategories", "holdings", "reminder_categories"):
        assert count(tgt, t) == count(engine, t)
    # the starter rows the template already had were replaced, not added to
    tables2, bad2 = copy_all(engine, tgt)
    assert bad2 == [] and count(tgt, "categories") == count(engine, "categories")
    tgt.dispose()


def test_copy_keeps_fractions_in_sqlite_integer_columns(template, tmp_path):
    """SQLite's INTEGER columns hold fractions (real data: category_targets.target_pct = 16.25322525); a copy into
    SQLite must keep them, not truncate them to 16."""
    from db.replicate import copy_all
    src = create_engine(f"sqlite:///{fresh_sqlite(template, tmp_path, 'src.db')}")
    with src.begin() as c:
        c.execute(text("INSERT INTO category_targets (category_id, from_month, target_pct) "
                       "VALUES ((SELECT MIN(id) FROM categories), '2026-10', 16.25322525)"))
    tgt = create_engine(f"sqlite:///{fresh_sqlite(template, tmp_path, 'tgt.db')}")
    _, bad = copy_all(src, tgt)
    assert bad == []
    with tgt.connect() as c:
        assert c.execute(text("SELECT target_pct FROM category_targets WHERE from_month = '2026-10'")).scalar() == 16.25322525
    src.dispose()
    tgt.dispose()


def _postgres_url():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    env_file = ROOT / ".env.local"
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TEST_DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    return url


def test_copy_into_postgres_resets_sequences(mirror_file):
    """SQLite -> PostgreSQL (what tools/copy_to_postgres.py does), inside a scratch schema of the test database."""
    from sqlalchemy.engine import make_url
    from db.replicate import build_schema, copy_all
    base = _postgres_url()
    if not base:
        pytest.skip("no PostgreSQL test database configured")
    schema = f"replicate_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base)
    with admin.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        url = make_url(base).update_query_dict({"options": f"-csearch_path={schema}"})
        build_schema(url.render_as_string(hide_password=False))
        tgt = create_engine(url)
        src = create_engine(f"sqlite:///{mirror_file}")
        tables, bad = copy_all(src, tgt)
        assert bad == []
        with tgt.begin() as c:
            top = c.execute(text("SELECT MAX(id) FROM categories")).scalar()
            new = c.execute(text("INSERT INTO categories (name, user_id) VALUES ('ZZ seq check', 1) RETURNING id")).scalar()
        assert new == top + 1, "the id sequence continues after the copied ids"
        src.dispose()
        tgt.dispose()
    finally:
        with admin.begin() as c:
            c.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


# ---- mirror -----------------------------------------------------------------------------------------------

def make_mirror(path, template, **kw):
    from db.engine import engine
    from db.mirror import Mirror

    def build(url, p):  # reuse the module template instead of running Alembic again
        shutil.copyfile(template, p)
    return Mirror(engine, path, build_schema=build, **kw)


def test_mirror_refresh_keeps_the_old_file_once(seeded_db, template, tmp_path):
    from db.engine import engine
    path = tmp_path / "spendlens_v2.db"
    old = create_engine(f"sqlite:///{path}")
    with old.begin() as c:
        c.execute(text("CREATE TABLE marker (v TEXT)"))
        c.execute(text("INSERT INTO marker VALUES ('old data')"))
    old.dispose()
    m = make_mirror(path, template)
    assert m.status()["updated_at"] is None
    assert m.run() is True
    bak = tmp_path / "spendlens_v2.pre-postgres.bak"
    assert bak.exists()
    kept = create_engine(f"sqlite:///{bak}")
    with kept.connect() as c:
        assert c.execute(text("SELECT v FROM marker")).scalar() == "old data"
    kept.dispose()
    mirrored = create_engine(f"sqlite:///{path}")
    assert count(mirrored, "categories") == count(engine, "categories")
    mirrored.dispose()
    st = m.status()
    assert st["updated_at"] and st["last_error"] is None and st["path_name"] == "spendlens_v2.db"
    first = bak.stat().st_mtime_ns
    assert m.run() is True
    assert bak.stat().st_mtime_ns == first, "the backup is taken only before the first mirror"
    bak.unlink()
    assert m.run() is True
    assert not bak.exists(), "an earlier mirror is never mistaken for the old database"
    assert not list(tmp_path.glob("*.tmp-*"))


def test_mirror_keeps_old_copy_when_file_is_locked(seeded_db, template, tmp_path, monkeypatch):
    import db.mirror as mirror_mod
    path = tmp_path / "spendlens_v2.db"
    m = make_mirror(path, template)
    assert m.run() is True
    before = path.read_bytes()

    def locked(src, dst):
        raise PermissionError("in use")
    m._swap = locked
    monkeypatch.setattr(mirror_mod.time, "sleep", lambda s: None)
    assert m.run() is False
    assert path.read_bytes() == before
    assert "locked" in m.status()["last_error"]
    assert not list(tmp_path.glob("*.tmp-*"))


def test_mirror_debounces_commits(seeded_db, template, tmp_path):
    m = make_mirror(tmp_path / "m.db", template, debounce=0.4, period=60)
    runs = []
    m.run = lambda **kw: runs.append(time.monotonic()) or True
    m.start()
    try:
        for _ in range(3):
            m.mark_dirty()
            time.sleep(0.1)
        time.sleep(0.2)
        assert runs == [], "still inside the debounce window"
        time.sleep(0.6)
        assert len(runs) == 1, "three quick commits give one refresh"
        m.mark_dirty()
        time.sleep(0.8)
        assert len(runs) == 2
    finally:
        m.stop(final=False)


def test_mirror_skips_while_paused(seeded_db, template, tmp_path):
    m = make_mirror(tmp_path / "m.db", template, debounce=0.1, period=60)
    m.paused = lambda: True
    calls = []
    m.run = lambda **kw: calls.append(1) or True
    m.start()
    m.mark_dirty()
    time.sleep(0.4)
    m.stop(final=True)
    assert calls == []


# ---- failover ---------------------------------------------------------------------------------------------

@pytest.fixture
def fallback(seeded_db, mirror_file, tmp_path, monkeypatch):
    """The app with PostgreSQL unreachable and (a copy of) the mirror in place. Restores the real binding afterwards."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from db import failover
    from db.engine import SessionLocal, engine
    from db.mirror import Mirror
    from routes.api import router

    down = create_engine(UNREACHABLE, connect_args={"connect_timeout": 1})
    mine = tmp_path / "mirror.db"
    shutil.copyfile(mirror_file, mine)
    fo = failover.Failover(down, SessionLocal, Mirror(down, mine))
    monkeypatch.setattr(failover, "_instance", fo)
    app = FastAPI()
    failover.install(app)
    app.include_router(router)
    try:
        yield fo, TestClient(app, cookies={"sl_session": ADMIN_TOKEN}), app
    finally:
        if fo.pg_sync is not None:
            fo.pg_sync.stop(final=False)
        SessionLocal.configure(bind=engine)
        SessionLocal.class_ = Session
        fo._close_mirror_engine()
        if fo._rw_engine is not None:
            fo._rw_engine.dispose()
        down.dispose()


def test_unreachable_primary_switches_to_the_mirror(fallback):
    fo, client, app = fallback
    assert fo.check() is False
    st = client.get("/spendlens/api/status").json()
    assert st["primary"] == "postgresql" and st["mode"] == "read-only-fallback"
    assert st["mirror"]["path_name"] == "mirror.db"
    cats = client.get("/spendlens/api/categories")
    assert cats.status_code == 200 and len(cats.json()) > 0
    r = client.post("/spendlens/api/categories", json={"name": "Not allowed", "icon": "x", "color": "#000000"})
    assert r.status_code == 503 and "read-only copy" in r.json()["detail"]
    for method in ("put", "delete"):
        assert getattr(client, method)("/spendlens/api/reminders/1").status_code == 503


def test_every_read_works_on_the_read_only_mirror(fallback):
    """No GET may write: due SIPs, snapshots, starter goals and price refreshes are skipped on the mirror."""
    fo, client, app = fallback
    fo.check()
    paths = [p for p, ops in app.openapi()["paths"].items()
             if "get" in ops and "{" not in p and p.startswith("/spendlens/api")]
    assert len(paths) > 30
    for p in paths + ["/spendlens/api/expenses/monthly-grid?month=2026-10", "/spendlens/api/reminders/calendar?month=2026-10"]:
        r = client.get(p)
        assert r.status_code < 500, (p, r.status_code, r.text[:200])


def test_background_writes_are_skipped(fallback):
    import sip
    import portfolio as pf
    from db.engine import SessionLocal
    from routes.investing_routes import refresh_and_snapshot
    fo, _, _ = fallback
    fo.check()
    s = SessionLocal()
    try:
        assert sip.apply_due_sips(s) == 0
        assert pf.record_snapshot(s, []) is None
    finally:
        s.close()
    assert refresh_and_snapshot() is None


def test_recovery_switches_back(fallback):
    from db.engine import SessionLocal, engine
    fo, client, app = fallback
    fo.check()
    assert fo.read_only()
    fo.primary = engine  # the "PostgreSQL" is reachable again
    assert fo.check() is True
    assert not fo.read_only() and client.get("/spendlens/api/status").json()["mode"] == "normal"
    assert SessionLocal.kw["bind"] is engine


def test_no_mirror_means_no_fallback(seeded_db, tmp_path):
    from db import failover
    from db.engine import SessionLocal, engine
    from db.mirror import Mirror
    down = create_engine(UNREACHABLE, connect_args={"connect_timeout": 1})
    fo = failover.Failover(down, SessionLocal, Mirror(down, tmp_path / "missing.db"))
    assert fo.check() is False and not fo.read_only()
    assert SessionLocal.kw["bind"] is engine
    down.dispose()


@pytest.mark.skipif(ON_POSTGRES, reason="SQLite as the primary")
def test_sqlite_primary_has_no_mirror_or_fallback(client):
    from db import failover
    assert failover.startup() is None
    assert failover._instance is None and not failover.read_only()
    st = client.get("/spendlens/api/status").json()
    assert st["primary"] == "sqlite" and st["mode"] == "normal" and st["can_switch"] is False and st["mirror"] is None
    r = client.post("/spendlens/api/database/switch", json={"to": "postgresql"})
    assert r.status_code == 409 and "isn't configured" in r.json()["detail"]


# ---- switching the main database --------------------------------------------------------------------------

@pytest.fixture
def switchable(seeded_db, template, tmp_path, monkeypatch):
    """The app on a 'PostgreSQL' (a second SQLite file stands in for it, so this runs anywhere) with its copy."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from db import failover
    from db.engine import SessionLocal, engine
    from db.mirror import Mirror
    from db.replicate import copy_all
    from routes.api import router

    main_path = fresh_sqlite(template, tmp_path, "main.db")
    pg = create_engine(f"sqlite:///{main_path}", connect_args={"check_same_thread": False})
    assert copy_all(engine, pg)[1] == []
    mirror = Mirror(pg, tmp_path / "copy.db", build_schema=lambda url, p: shutil.copyfile(template, p))
    fo = failover.Failover(pg, SessionLocal, mirror)
    SessionLocal.configure(bind=pg)
    monkeypatch.setattr(failover, "_instance", fo)
    app = FastAPI()
    failover.install(app)
    app.include_router(router)
    try:
        yield fo, TestClient(app, cookies={"sl_session": ADMIN_TOKEN}), pg, tmp_path / "copy.db"
    finally:
        if fo.pg_sync is not None:
            fo.pg_sync.stop(final=False)
        SessionLocal.configure(bind=engine)
        SessionLocal.class_ = Session
        for e in (fo._rw_engine, fo._ro_engine, pg):
            if e is not None:
                e.dispose()


def names(eng):
    with eng.connect() as c:
        return {r[0] for r in c.execute(text("SELECT name FROM categories"))}


def test_switch_round_trip_keeps_both_databases_identical(switchable):
    from db.replicate import table_digest
    fo, client, pg, copy_path = switchable
    assert client.get("/spendlens/api/status").json()["primary"] == "postgresql"

    r = client.post("/spendlens/api/database/switch", json={"to": "sqlite"})
    assert r.status_code == 200 and r.json()["primary"] == "sqlite" and r.json()["copy"]["to"] == "postgresql"
    assert fo.saved_mode() == "sqlite", "the choice survives a restart"
    made = client.post("/spendlens/api/categories", json={"name": "Saved while on SQLite", "icon": "x", "color": "#123456"})
    assert made.status_code in (200, 201)
    lite = create_engine(f"sqlite:///{copy_path}")
    assert "Saved while on SQLite" in names(lite) and "Saved while on SQLite" not in names(pg)

    r = client.post("/spendlens/api/database/switch", json={"to": "postgresql"})
    assert r.status_code == 200 and r.json()["primary"] == "postgresql"
    assert "Saved while on SQLite" in names(pg), "switching back copies what was saved in SQLite"
    made = client.post("/spendlens/api/categories", json={"name": "Saved on PostgreSQL", "icon": "x", "color": "#654321"})
    assert made.status_code in (200, 201)
    lite.dispose()
    assert fo.mirror.run(wait=True)
    lite = create_engine(f"sqlite:///{copy_path}")
    from sqlalchemy import MetaData
    m1, m2 = MetaData(), MetaData()
    m1.reflect(bind=pg)
    m2.reflect(bind=lite)
    with pg.connect() as a, lite.connect() as b:
        for name in ("categories", "subcategories", "holdings", "expenses"):
            cols = [c.name for c in m1.tables[name].columns]
            assert table_digest(a, m1.tables[name], cols) == table_digest(b, m2.tables[name], cols), name
    lite.dispose()
    assert fo.saved_mode() == "postgresql"


def test_switch_refusals_and_pause(switchable):
    fo, client, _, _ = switchable
    assert client.post("/spendlens/api/database/switch", json={"to": "postgresql"}).json()["primary"] == "postgresql"
    assert client.post("/spendlens/api/database/switch", json={"to": "mysql"}).status_code == 400
    assert client.post("/spendlens/api/database/switch", json={"to": "sqlite"}).status_code == 200
    fo.primary_ok = lambda: False
    r = client.post("/spendlens/api/database/switch", json={"to": "postgresql"})
    assert r.status_code == 409 and "can't be reached" in r.json()["detail"]
    assert client.get("/spendlens/api/categories").status_code == 200, "a refused switch leaves SQLite working"
    fo.switching = True
    try:
        assert client.get("/spendlens/api/categories").status_code == 503
        assert client.get("/spendlens/api/status").status_code == 200
    finally:
        fo.switching = False


def test_fallback_can_switch_to_sqlite_and_keep_saving(fallback):
    fo, client, _ = fallback
    fo.check()
    assert fo.read_only()
    r = client.post("/spendlens/api/database/switch", json={"to": "sqlite"})
    assert r.status_code == 200 and r.json()["primary"] == "sqlite" and r.json()["mode"] == "normal"
    made = client.post("/spendlens/api/categories", json={"name": "Saved during the outage", "icon": "x", "color": "#111111"})
    assert made.status_code in (200, 201)


# ---- sync tracking: log, exact change counts, overview, abnormalities, comparison --------------------------

def test_diff_snapshots_counts_added_changed_removed():
    from db.replicate import diff_snapshots
    old = {"t": {"1": "a", "2": "b", "3": "c"}, "gone": {"9": "z"}}
    new = {"t": {"1": "a", "2": "B", "4": "d"}, "same": {}}
    assert diff_snapshots(old, new) == {"t": (1, 1, 1), "gone": (0, 0, 1)}
    assert diff_snapshots(None, {"t": {"1": "a"}}) == {"t": (1, 0, 0)}


def test_sync_log_records_prunes_and_summarises(tmp_path):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import insert
    from db.synclog import SyncLog, runs
    log = SyncLog(tmp_path / "ops.db")
    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat(timespec="seconds")
    with log.engine.begin() as c:
        c.execute(insert(runs).values(at=old, direction="d", trigger="save", ok=1, duration_ms=1))
    log.record_run("postgresql→sqlite", "save", True, 1200, totals={"a": 5, "b": 2}, changes={"a": (2, 1, 0)})
    log.record_run("postgresql→sqlite", "periodic", False, 300, error="boom")
    rs = log.recent_runs()
    assert len(rs) == 2, "rows older than 90 days are pruned"
    assert rs[0]["ok"] is False and rs[0]["error"] == "boom" and log.consecutive_failures() == 1
    good = log.last_run(ok=True)
    assert (good["rows_total"], good["rows_added"], good["rows_changed"], good["tables_changed"]) == (7, 2, 1, 1)
    assert good["detail"] == {"a": [5, 2, 1, 0], "b": [2, 0, 0, 0]}
    week = log.since((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds"))
    assert week == {"syncs": 2, "failed": 1, "rows_changed": 3, "tables_changed": 1}
    days = log.daily(14)
    assert len(days) == 14 and days[-1]["syncs"] == 2 and days[-1]["failed"] == 1
    log.save_snapshot("x", {"a": {"1": "h"}})
    assert log.last_snapshot("x") == {"a": {"1": "h"}} and log.last_snapshot("y") is None
    log.engine.dispose()


def test_each_copy_records_exactly_what_changed(switchable):
    fo, client, pg, _ = switchable
    assert fo.mirror.run(trigger="startup")
    first = fo.log.last_run()
    assert first["ok"] and first["trigger"] == "startup" and first["tables_changed"] is None and first["rows_added"] == 0, \
        "the very first copy is the starting point, not thousands of 'added' rows"
    with pg.begin() as c:
        c.execute(text("INSERT INTO categories (name, user_id) VALUES ('ZZ new', 1), ('ZZ doomed', 1)"))
    assert fo.mirror.run()
    with pg.begin() as c:
        c.execute(text("UPDATE categories SET icon = 'Q' WHERE name = 'ZZ new'"))
        c.execute(text("DELETE FROM categories WHERE name = 'ZZ doomed'"))
    assert fo.mirror.run(trigger="save")
    last = fo.log.last_run()
    assert last["detail"]["categories"][1:] == [0, 1, 1], "one changed, one removed"
    assert (last["rows_added"], last["rows_changed"], last["rows_removed"], last["tables_changed"]) == (0, 1, 1, 1)


def test_overview_kpis_and_tables(switchable):
    fo, client, pg, _ = switchable
    assert fo.mirror.run(trigger="startup")
    ov = client.get("/spendlens/api/database/overview").json()
    assert ov["primary"] == "postgresql" and ov["main"]["role"] == "main" and ov["copy"]["kind"] == "sqlite"
    assert ov["main"]["reachable"] and ov["copy"]["reachable"]
    k = ov["kpis"]
    assert k["last_sync"]["ok"] and k["pending"] == 0 and k["health_7d"]["failed"] == 0
    assert k["in_sync"]["matching"] == k["in_sync"]["tables"] >= 30
    assert {t["area"] for t in ov["tables"]} >= {"Expense & budget", "Portfolio", "Credit cards", "Calendar"}
    assert ov["abnormalities"] == [], ov["abnormalities"]
    hist = client.get("/spendlens/api/database/history").json()
    assert len(hist["days"]) == 14 and hist["runs"][0]["trigger"] == "startup" and hist["keep_days"] == 90


def test_abnormalities_are_flagged(switchable):
    fo, client, pg, copy_path = switchable
    assert fo.mirror.run()
    lite = create_engine(f"sqlite:///{copy_path}")
    with lite.begin() as c:  # the copy loses rows behind the app's back
        c.execute(text("DELETE FROM subcategory_rules"))
    lite.dispose()
    ov = client.get("/spendlens/api/database/overview").json()
    titles = [a["title"] for a in ov["abnormalities"]]
    assert any(t.startswith("Row counts differ") for t in titles), titles
    assert ov["abnormalities"][0]["level"] == "critical"
    cmp = client.post("/spendlens/api/database/compare").json()
    assert cmp["ok"] is False and cmp["differs"] >= 1 and cmp["pending"] == 0
    assert [t for t in cmp["tables"] if not t["match"]][0]["name"] == "subcategory_rules"
    titles = [a["title"] for a in client.get("/spendlens/api/database/overview").json()["abnormalities"]]
    assert any("comparison found" in t for t in titles)
    assert fo.mirror.run()  # the next copy repairs it
    assert client.post("/spendlens/api/database/compare").json()["ok"] is True
    fo.log.record_run("postgresql→sqlite", "save", False, 50, error="disk full")
    titles = [a["title"] for a in client.get("/spendlens/api/database/overview").json()["abnormalities"]]
    assert "The last sync failed" in titles


def test_switches_are_logged(switchable):
    fo, client, _, _ = switchable
    assert client.post("/spendlens/api/database/switch", json={"to": "sqlite"}).status_code == 200
    fo.primary_ok = lambda: False
    assert client.post("/spendlens/api/database/switch", json={"to": "postgresql"}).status_code == 409
    sw = client.get("/spendlens/api/database/history").json()["switches"]
    assert sw[0]["ok"] is False and "can't be reached" in sw[0]["error"]
    assert sw[1]["ok"] is True and sw[1]["to_kind"] == "sqlite" and sw[1]["rows_total"] > 0


def test_saves_schedule_a_copy_after_fallback_and_switches(switchable, monkeypatch):
    """Regression: the after-commit hook must survive SessionLocal's class being swapped (fallback, switches)."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from db import failover
    from db.engine import SessionLocal
    fo, client, pg, _ = switchable
    event.listen(Session, "after_commit", failover._after_commit)
    try:
        def save():
            s = SessionLocal()
            s.execute(text("INSERT INTO categories (name, user_id) VALUES ('ZZ hook', 1)"))
            s.commit()
            s.close()
        fo.mirror.pending = 0
        save()
        assert fo.mirror.pending == 1 and fo.mirror._dirty_at is not None
        assert fo.mirror.run()
        assert client.post("/spendlens/api/database/switch", json={"to": "sqlite"}).status_code == 200
        save()
        assert fo.pg_sync.pending == 1, "a save on SQLite schedules the copy into PostgreSQL"
        assert client.post("/spendlens/api/database/switch", json={"to": "postgresql"}).status_code == 200
        before = fo.mirror.pending
        save()
        assert fo.mirror.pending == before + 1, "and back on PostgreSQL, the copy into SQLite"
    finally:
        event.remove(Session, "after_commit", failover._after_commit)
