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

IS_POSTGRES = DATABASE_URL.startswith("postgresql")

# check_same_thread=False only matters for SQLite. On PostgreSQL a short connect timeout lets db/failover.py notice
# an unreachable server quickly, and pre-ping replaces pooled connections that died with a server restart.
if IS_POSTGRES:
    engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 3}, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """Per-request session, injected with FastAPI's `Depends`; closed even if the route raises."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
