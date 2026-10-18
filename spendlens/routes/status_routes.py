from fastapi import APIRouter

from db import failover

router = APIRouter(prefix="/spendlens/api", tags=["status"])


@router.get("/status")
def database_status():
    """Which database is serving requests: PostgreSQL normally, the read-only SQLite mirror while it is down."""
    return failover.status()
