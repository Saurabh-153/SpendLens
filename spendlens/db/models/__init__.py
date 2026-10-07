"""Importing this package registers every model on Base.metadata, for Alembic autogenerate.

Models are split by domain to mirror routes/*_routes.py. Only the portfolio domain exists
so far; expense/cards/settings land in later phases of the SQLAlchemy migration.
"""
from .portfolio import (  # noqa: F401
    Holding,
    HoldingGroup,
    HoldingSnapshot,
    PortfolioSnapshot,
    PortfolioGoal,
    PortfolioPlan,
)
