from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import failover, syncstats

router = APIRouter(prefix="/spendlens/api", tags=["status"])


@router.get("/status")
def database_status():
    """Which database is the main one, when the other was last brought up to date, and whether it is read-only."""
    return failover.status()


class SwitchRequest(BaseModel):
    to: str


@router.post("/database/switch")
def switch_database(data: SwitchRequest):
    """Make SQLite or PostgreSQL the main database. Everything is copied into it first and checked; saving is
    paused for those few seconds. Afterwards the other one is kept up to date as the copy."""
    try:
        return failover.switch(data.to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except failover.SwitchError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _instance_or_basic():
    fo = failover._instance
    if fo is None:
        return None, {**failover.status(), "main": {"kind": "sqlite", "name": "SQLite", "role": "main"}, "copy": None,
                      "kpis": None, "tables": [], "last_compare": None, "abnormalities": []}
    return fo, None


@router.get("/database/overview")
def database_overview():
    """Settings › Database: KPIs, both databases, every table's row counts on both sides, and anything abnormal."""
    fo, basic = _instance_or_basic()
    return basic if fo is None else syncstats.overview(fo)


@router.get("/database/history")
def database_history(days: int = 14):
    """Rows synced per day, the recent copies and the switches (kept for 90 days)."""
    fo, _ = _instance_or_basic()
    if fo is None:
        return {"days": [], "runs": [], "switches": [], "keep_days": 90}
    return syncstats.history(fo, max(1, min(days, 90)))


@router.post("/database/compare")
def database_compare():
    """Compare every table in both databases row by row (count + checksum), and record the result."""
    fo, _ = _instance_or_basic()
    if fo is None:
        raise HTTPException(status_code=409, detail="There is only one database (SQLite), so there is nothing to compare.")
    try:
        return syncstats.compare(fo)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
