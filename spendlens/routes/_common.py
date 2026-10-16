"""Shared by every routes/*_routes.py module: the connection-lifecycle dependency, and a helper
for routes that are partway through the SQLAlchemy cutover (some of their own queries on ORM
models, others - complex joins, or tables not modeled yet - still on the raw connection)."""
from database import get_db
from db.base import row_dict  # noqa: F401  (re-exported: routes import it from here)


def get_db_dep():
    """Per-request connection, injected with FastAPI's `Depends`. The `finally` runs even if the
    route raises, so a connection is never left open on an error path (unlike a bare `db.close()`
    at the end of the function, which an exception would skip)."""
    db = get_db()
    try:
        yield db
    finally:
        db.close()

