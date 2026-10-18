"""The SQLite mirror of the PostgreSQL primary and the read-only fallback onto it (db/replicate.py, db/mirror.py,
db/failover.py). Everything here runs on temp files, and on PostgreSQL only inside a throwaway schema."""
import os
import shutil
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from conftest import ON_POSTGRES, ROOT

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
    m.run = lambda: runs.append(time.monotonic()) or True
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
    m.run = lambda: calls.append(1) or True
    m.start()
    m.mark_dirty()
    time.sleep(0.4)
    m.stop(final=True)
    assert calls == []


# ---- failover ---------------------------------------------------------------------------------------------

@pytest.fixture
def fallback(seeded_db, mirror_file, monkeypatch):
    """The app with PostgreSQL unreachable and the mirror in place. Restores the real binding afterwards."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from db import failover
    from db.engine import SessionLocal, engine
    from db.mirror import Mirror
    from routes.api import router

    down = create_engine(UNREACHABLE, connect_args={"connect_timeout": 1})
    fo = failover.Failover(down, SessionLocal, Mirror(down, mirror_file))
    monkeypatch.setattr(failover, "_instance", fo)
    app = FastAPI()
    failover.install(app)
    app.include_router(router)
    try:
        yield fo, TestClient(app), app
    finally:
        SessionLocal.configure(bind=engine)
        SessionLocal.class_ = Session
        fo._close_mirror_engine()
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
    assert client.get("/spendlens/api/status").json() == {"primary": "sqlite", "mode": "normal", "mirror": None}
