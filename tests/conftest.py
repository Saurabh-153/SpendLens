"""Test fixtures.

The suite NEVER touches `spendlens/spendlens_v2.db`. By default it runs on a throwaway SQLite file in a temp
directory (`SPENDLENS_DB`, which `database.DB_PATH` and `db.engine` pick up at import time).

Set TEST_DATABASE_URL (or SPENDLENS_TEST_PG=1 to read TEST_DATABASE_URL from the repo's .env.local) to run the same
suite on PostgreSQL instead. That database is wiped and rebuilt by Alembic at the start of the run, so it must be
a database kept for tests: its name has to end in `_test`.

A test that wants your real data gets a *copy* of it (`real_db_copy`), and is skipped when the file is not there
or when the suite runs on PostgreSQL (those tests are about the SQLite file itself).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "spendlens"
REAL_DB = BACKEND / "spendlens_v2.db"


def _test_database_url():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url and os.environ.get("SPENDLENS_TEST_PG") == "1":
        env_file = ROOT / ".env.local"
        for line in env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []:
            if line.startswith("TEST_DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    return url


# Must happen before `database` / `db.engine` are imported anywhere: they read these at import time.
_TMP = Path(tempfile.mkdtemp(prefix="spendlens-tests-"))
os.environ["SPENDLENS_DB"] = str(_TMP / "fixture.db")
PG_URL = _test_database_url()
if PG_URL:
    os.environ["DATABASE_URL"] = PG_URL
else:
    os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ON_POSTGRES = bool(PG_URL)
sqlite_only = pytest.mark.skipif(ON_POSTGRES, reason="about the SQLite file itself")


#: A small, deterministic portfolio: one of each shape the valuation code handles, with
#: SIPs, so the exposure and mix endpoints have something real to compute. Values are
#: round numbers chosen to make the expected mix obvious by hand: 60/10/30 of ₹10L.
FIXTURE_HOLDINGS = [
    # name, ticker, asset_type, exposure, grp, qty, buy_price, cmp, units, nav, sip
    ("Fixture Large Cap Fund", "", "MF", "Equity", "Mutual Funds", 1, 400000, 600000, 1000, 600, 20000),
    ("Fixture Gold ETF", "GOLDBEES", "GOLD", "Gold", "Gold", 1000, 70, 100, 0, 0, 5000),
    ("Fixture Bank FD", "", "FD", "Debt", "Fixed Deposits", 1, 250000, 300000, 0, 0, 0),
]


def _reset_postgres(engine):
    from sqlalchemy import text
    name = engine.url.database or ""
    assert name.endswith("_test"), f"refusing to wipe {name!r}: the test database's name must end in _test"
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def seeded_db():
    """A freshly built database: Alembic's schema and starter data (the same path app.py runs - see db/migrate.py),
    plus FIXTURE_HOLDINGS. Returns the SQLite file's path, or the PostgreSQL URL."""
    from sqlalchemy import text
    from db.engine import engine
    from db.migrate import prepare_database
    if ON_POSTGRES:
        _reset_postgres(engine)
    prepare_database()
    cols = ("name", "ticker", "asset_type", "exposure", "grp", "qty", "buy_price", "cmp", "units", "nav", "sip_amount")
    with engine.begin() as c:
        if c.execute(text("SELECT COUNT(*) FROM holdings")).scalar() == 0:
            c.execute(text(f"INSERT INTO holdings ({', '.join(cols)}, manual) VALUES ({', '.join(':' + k for k in cols)}, 1)"),
                      [dict(zip(cols, h)) for h in FIXTURE_HOLDINGS])
    return PG_URL if ON_POSTGRES else Path(engine.url.database)


@pytest.fixture(scope="session")
def client(seeded_db):
    """A TestClient over the real router, without app.py's price scheduler."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def blank_db(tmp_path, monkeypatch):
    """An empty file at a fresh path, for migration tests. Yields the path."""
    if ON_POSTGRES:
        pytest.skip("about the SQLite file itself")
    import database
    path = tmp_path / "blank.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return path


@pytest.fixture
def real_db_copy(tmp_path, monkeypatch):
    """A copy of the user's real database, so migrations can be rehearsed on real data."""
    if ON_POSTGRES:
        pytest.skip("about the SQLite file itself")
    if not REAL_DB.exists() or REAL_DB.stat().st_size == 0:
        pytest.skip("no real database to copy")
    import database
    path = tmp_path / "real-copy.db"
    shutil.copy2(REAL_DB, path)
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return path


@pytest.fixture
def unmigrated_db(real_db_copy):
    """A copy of the real database rewound to before the numbered migrations.

    The real file may already be fully migrated, so the record is dropped rather than
    assumed: these tests are about the migration mechanism, not the current state.
    """
    import sqlite3
    conn = sqlite3.connect(str(real_db_copy))
    conn.execute("DROP TABLE IF EXISTS schema_migrations")
    conn.commit()
    conn.close()
    return real_db_copy
