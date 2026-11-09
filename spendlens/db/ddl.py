"""Dialect-aware bits of DDL shared by the Alembic revisions, so one migration runs on SQLite and PostgreSQL."""
import sqlalchemy as sa


def is_sqlite(bind):
    return bind.dialect.name == "sqlite"


def now_text(bind):
    """Server default writing the current UTC time as 'YYYY-MM-DD HH:MM:SS' text (SQLite's datetime('now'))."""
    if is_sqlite(bind):
        return sa.text("(datetime('now'))")
    return sa.text("(to_char(timezone('UTC', now()), 'YYYY-MM-DD HH24:MI:SS'))")


def today_text(bind):
    """Server default writing today's UTC date as 'YYYY-MM-DD' text (SQLite's date('now'))."""
    if is_sqlite(bind):
        return sa.text("(date('now'))")
    return sa.text("(to_char(timezone('UTC', now()), 'YYYY-MM-DD'))")


def int_or_float():
    """INTEGER on SQLite (as the tables were always declared there, where the column still holds fractional values),
    double precision elsewhere so those fractional values survive."""
    return sa.Integer().with_variant(sa.Float(), "postgresql")


def sync_sequences(bind, tables):
    """After rows were inserted with explicit ids, move PostgreSQL's id sequences past them. No-op on SQLite."""
    if bind.dialect.name != "postgresql":
        return
    for t in tables:
        bind.execute(sa.text(
            f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"))


def table_names(bind):
    return set(sa.inspect(bind).get_table_names())
