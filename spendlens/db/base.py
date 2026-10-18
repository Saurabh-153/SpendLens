"""Declarative base every SQLAlchemy model inherits from. Alembic's env.py imports
`Base.metadata` from here to autogenerate migrations against the models."""
from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def row_dict(obj):
    """ORM instance -> plain dict of its columns, so it can feed code written for a sqlite3.Row
    (dict(row), row["col"]) and be returned straight from a route."""
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def utc_now_text():
    """'YYYY-MM-DD HH:MM:SS' in UTC: the format SQLite's datetime('now') wrote, set in Python so every dialect stores the same text."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
