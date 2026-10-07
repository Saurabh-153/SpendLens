"""Shared by every routes/*_routes.py module: one connection-lifecycle dependency."""
from database import get_db


def get_db_dep():
    """Per-request connection, injected with FastAPI's `Depends`. The `finally` runs even if the
    route raises, so a connection is never left open on an error path (unlike a bare `db.close()`
    at the end of the function, which an exception would skip)."""
    db = get_db()
    try:
        yield db
    finally:
        db.close()
