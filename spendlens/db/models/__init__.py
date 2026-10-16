"""Importing this package registers every model on Base.metadata, for Alembic autogenerate.

Models are split by domain to mirror routes/*_routes.py.
"""
from .portfolio import (  # noqa: F401
    Holding,
    HoldingGroup,
    HoldingSnapshot,
    PortfolioSnapshot,
    PortfolioGoal,
    PortfolioPlan,
)
from .expense import (  # noqa: F401
    Category,
    CategoryTarget,
    BudgetHistory,
    Expense,
    Subcategory,
    SubcategoryRule,
    Settings,
)
from .cards import (  # noqa: F401
    CardAccount,
    Card,
    CardStatement,
    CardTxn,
    CardMerchantRule,
    CardPerk,
)
