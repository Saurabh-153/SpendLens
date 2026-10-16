"""Test fixtures.

The suite NEVER touches `spendlens/spendlens_v2.db`. Before anything is imported, this
file points `SPENDLENS_DB` at a throwaway file in a temp directory, which
`database.DB_PATH` picks up. A test that wants your real data gets a *copy* of it
(`real_db_copy`), and is skipped when the file is not there.
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

# Must happen before `database` is imported anywhere: it reads the env var at import time.
_TMP = Path(tempfile.mkdtemp(prefix="spendlens-tests-"))
os.environ["SPENDLENS_DB"] = str(_TMP / "fixture.db")
sys.path.insert(0, str(BACKEND))


#: A small, deterministic portfolio: one of each shape the valuation code handles, with
#: SIPs, so the exposure and mix endpoints have something real to compute. Values are
#: round numbers chosen to make the expected mix obvious by hand: 60/10/30 of ₹10L.
FIXTURE_HOLDINGS = [
    # name, ticker, asset_type, exposure, grp, qty, buy_price, cmp, units, nav, sip
    ("Fixture Large Cap Fund", "", "MF", "Equity", "Mutual Funds", 1, 400000, 600000, 1000, 600, 20000),
    ("Fixture Gold ETF", "GOLDBEES", "GOLD", "Gold", "Gold", 1000, 70, 100, 0, 0, 5000),
    ("Fixture Bank FD", "", "FD", "Debt", "Fixed Deposits", 1, 250000, 300000, 0, 0, 0),
]


@pytest.fixture(scope="session")
def seeded_db():
    """A freshly seeded database: the schema, init_db's seed data, Alembic's migrations on
    top (same sequence app.py runs - see db/migrate.py), and FIXTURE_HOLDINGS."""
    import database
    from db.migrate import upgrade_head
    database.init_db()
    upgrade_head()
    conn = database.get_db()
    if conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0] == 0:
        conn.executemany(
            """INSERT INTO holdings (name, ticker, asset_type, exposure, grp, qty,
                                     buy_price, cmp, units, nav, sip_amount, manual)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""", FIXTURE_HOLDINGS)
        conn.commit()
    conn.close()
    return Path(database.DB_PATH)


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
    import database
    path = tmp_path / "blank.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return path


@pytest.fixture
def real_db_copy(tmp_path, monkeypatch):
    """A copy of the user's real database, so migrations can be rehearsed on real data."""
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
