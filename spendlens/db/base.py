"""Declarative base every SQLAlchemy model inherits from. Alembic's env.py imports
`Base.metadata` from here to autogenerate migrations against the models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def row_dict(obj):
    """ORM instance -> plain dict of its columns, so it can feed code written for a sqlite3.Row
    (dict(row), row["col"]) and be returned straight from a route."""
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
