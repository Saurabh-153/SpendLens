"""Declarative base every SQLAlchemy model inherits from. Alembic's env.py imports
`Base.metadata` from here to autogenerate migrations against the models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
