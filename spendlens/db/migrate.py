"""Brings the database to the current schema at startup (app.py) and for the tests (conftest.py).

Alembic owns the schema: `upgrade head` on an empty database (SQLite or PostgreSQL) builds every table and the
starter data (see the baseline revision). The one exception is an old SQLite file from before Alembic was added
(it has tables but no `alembic_version`): database.init_db() first brings it to the last hand-rolled schema, then
Alembic adopts it from the baseline. That legacy path is the only code left that uses the sqlite3 library.
"""
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic import command

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_ALEMBIC_DIR = _REPO_ROOT / "alembic"


def alembic_config():
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    return cfg


def upgrade_head():
    command.upgrade(alembic_config(), "head")


def is_legacy_sqlite(engine):
    """An SQLite file with tables but no alembic_version: built by the pre-Alembic init_db()."""
    if engine.dialect.name != "sqlite":
        return False
    names = set(sa.inspect(engine).get_table_names())
    return bool(names) and "alembic_version" not in names


def prepare_database():
    from db.engine import engine
    if is_legacy_sqlite(engine):
        import database
        database.init_db()
    upgrade_head()
