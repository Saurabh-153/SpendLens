"""Runs Alembic's migrations programmatically, so app.py (and conftest.py for tests) bring a
database to the same final schema through the same single path, instead of letting
database.py's hand-rolled MIGRATIONS and Alembic's own migrations drift apart - which is
exactly the bug class that broke the app against the real database earlier in this project.

Call order matters: run database.py's init_db()/run_migrations() FIRST (they create the
pre-multi-user baseline shape, including tables - like portfolio_snapshots - that only get
created lazily on first use otherwise), then upgrade_head() to apply the real ALTERs on top.
"""
from pathlib import Path

from alembic.config import Config
from alembic import command

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_ALEMBIC_DIR = _REPO_ROOT / "alembic"


def upgrade_head():
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    command.upgrade(cfg, "head")
