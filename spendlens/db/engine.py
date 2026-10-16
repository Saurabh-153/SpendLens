"""The one place that knows which database we're talking to.

`DATABASE_URL` picks the backend. Unset, it falls back to the same SQLite file
`database.py`'s raw-sqlite3 path already uses (`SPENDLENS_DB` env var, or
`spendlens_v2.db` next to this package) so existing data keeps working untouched
during the SQLAlchemy migration. Point it at `postgresql://...` later and nothing
else in this module needs to change.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_DEFAULT_SQLITE_PATH = os.environ.get("SPENDLENS_DB") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "spendlens_v2.db"
)

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{_DEFAULT_SQLITE_PATH}"

# check_same_thread=False only matters for the sqlite backend; SQLAlchemy ignores
# connect_args it doesn't recognise is not true for other dialects, so gate it.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """Per-request session, injected with FastAPI's `Depends`. Mirrors routes/_common.py's
    get_db_dep so the same connection-lifecycle guarantee (closed even on an exception) applies
    once routes move onto SQLAlchemy."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
