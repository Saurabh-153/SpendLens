"""Aggregates the three domain routers into the one router `app.py` mounts.

Routes used to all live in this one ~1,900-line file; they are now split by domain
(`expense_routes.py`, `investing_routes.py`, `card_routes.py`), each with its own
`APIRouter` under the same `/spendlens/api` prefix. This file just combines them, and
re-exports `refresh_and_snapshot` since `app.py` and the price scheduler both import it
from here.
"""
from fastapi import APIRouter

from .expense_routes import router as expense_router
from .investing_routes import router as investing_router, refresh_and_snapshot
from .card_routes import router as cards_router

router = APIRouter()
router.include_router(expense_router)
router.include_router(investing_router)
router.include_router(cards_router)

__all__ = ["router", "refresh_and_snapshot"]
