"""Copies every table between two SpendLens databases and verifies the copy, in either direction.

Used by tools/copy_to_postgres.py (SQLite -> PostgreSQL) and by db/mirror.py (PostgreSQL -> the SQLite mirror).
Both databases must already have the current schema (`build_schema`). The target is emptied first, the rows
are copied in foreign-key order with their values coerced to the target's column types (SQLite stores 0/1 for
booleans and does not enforce declared types), PostgreSQL id sequences are moved past the copied ids, and
finally every table is compared via an order-independent checksum. The source is only read, inside one
snapshot when it is PostgreSQL, so a copy taken while the app keeps writing is still consistent.
"""
import hashlib
import os
import subprocess
import sys

from sqlalchemy import Boolean, Float, Integer, MetaData, Numeric, String, Text, select, text

SPENDLENS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"alembic_version", "sqlite_sequence"}


class SchemaMismatch(Exception):
    pass


def build_schema(url, sqlite_path=None):
    """Run the app's own schema preparation (Alembic) for `url` in a child process, so that process's
    global engine points at `url` and nothing in this one is reconfigured (Alembic also resets logging)."""
    env = dict(os.environ, DATABASE_URL=url)
    if sqlite_path:
        env["SPENDLENS_DB"] = sqlite_path
    code = "import sys; sys.path.insert(0, '.'); from db.migrate import prepare_database; prepare_database()"
    r = subprocess.run([sys.executable, "-c", code], cwd=SPENDLENS, env=env, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"schema preparation failed: {(r.stderr or r.stdout).strip()[-800:]}")


def coerce(value, col_type, dialect="postgresql"):
    """The source value in the form the target column takes. Never loses information: SQLite keeps whatever it is
    given (its INTEGER columns hold fractions like category_targets.target_pct = 16.25), and a fraction headed for
    a PostgreSQL integer column is passed through so PostgreSQL refuses it rather than it being truncated."""
    if value is None or dialect == "sqlite":
        return value
    if isinstance(col_type, Boolean):
        return value if isinstance(value, bool) else bool(int(value))
    if isinstance(col_type, Integer):
        return int(value) if not isinstance(value, float) or value.is_integer() else value
    if isinstance(col_type, (Float, Numeric)):
        return float(value)
    if isinstance(col_type, (String, Text)):
        return value if isinstance(value, str) else str(value)
    return value


def normalise(value):
    """A value as both backends should agree on it, for the checksum."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):  # SQLite may hand back 2 where PostgreSQL's double gives 2.0
        value = round(value, 9) + 0.0
        return int(value) if value.is_integer() else value
    return value


def table_digest(conn, table, cols):
    """(row count, checksum) of a table, independent of row order and of either backend's collation."""
    rows = conn.execute(select(*[table.c[c] for c in cols])).all()
    h = hashlib.sha256()
    for line in sorted(repr(tuple(normalise(v) for v in r)) for r in rows):
        h.update(line.encode())
    return len(rows), h.hexdigest()


def _reflect(engine):
    meta = MetaData()
    meta.reflect(bind=engine)
    return meta


def copy_all(src, tgt, log=None):
    """Replace every table in `tgt` with the rows of `src`, then verify.

    Returns (tables, mismatches): the table names copied, in order, and [(name, source_rows, target_rows)] for
    every table whose checksum differs after the copy (empty when the copy is exact). `log(name, rows)` is called
    after each table. Raises SchemaMismatch if the two schemas do not have the same tables and columns."""
    src_meta, tgt_meta = _reflect(src), _reflect(tgt)
    tables = [t for t in tgt_meta.sorted_tables if t.name not in SKIP]
    missing = [t.name for t in tables if t.name not in src_meta.tables]
    extra = sorted(set(src_meta.tables) - set(tgt_meta.tables) - SKIP)
    if missing or extra:
        raise SchemaMismatch(f"Schemas differ. Missing in source: {missing}. Only in source: {extra}")
    for t in tables:
        absent = [c.name for c in t.columns if c.name not in src_meta.tables[t.name].c]
        if absent:
            raise SchemaMismatch(f"{t.name}: source lacks columns {absent}")

    source_digests = {}
    src_conn = src.connect()
    if src.dialect.name == "postgresql":
        src_conn = src_conn.execution_options(isolation_level="REPEATABLE READ")
    try:
        with src_conn.begin(), tgt.begin() as t:
            if tgt.dialect.name == "postgresql":
                t.execute(text("TRUNCATE " + ", ".join(f'"{x.name}"' for x in tables) + " RESTART IDENTITY CASCADE"))
            else:
                for table in reversed(tables):
                    t.execute(table.delete())
                if t.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'")).first():
                    t.execute(text("DELETE FROM sqlite_sequence"))
            for table in tables:
                stable = src_meta.tables[table.name]
                cols = [c.name for c in table.columns]
                rows = src_conn.execute(select(*[stable.c[c] for c in cols])).all()
                types = [table.c[c].type for c in cols]
                batch = [{c: coerce(v, ty, tgt.dialect.name) for c, v, ty in zip(cols, r, types)} for r in rows]
                for i in range(0, len(batch), 1000):
                    t.execute(table.insert(), batch[i:i + 1000])
                source_digests[table.name] = table_digest(src_conn, stable, cols)
                if log:
                    log(table.name, len(batch))
            if tgt.dialect.name == "postgresql":  # identity/serial counters must continue after the copied ids
                for table in tables:
                    pk = list(table.primary_key.columns)
                    if len(pk) == 1 and isinstance(pk[0].type, Integer):
                        seq = t.execute(text("SELECT pg_get_serial_sequence(:t, :c)"),
                                        {"t": table.name, "c": pk[0].name}).scalar()
                        if seq:
                            t.execute(text(f'SELECT setval(:s, COALESCE((SELECT MAX("{pk[0].name}") FROM "{table.name}"), 1), '
                                           f'(SELECT MAX("{pk[0].name}") FROM "{table.name}") IS NOT NULL)'), {"s": seq})
    finally:
        src_conn.close()

    mismatches = []
    with tgt.connect() as t:
        for table in tables:
            got = table_digest(t, table, [c.name for c in table.columns])
            if got != source_digests[table.name]:
                mismatches.append((table.name, source_digests[table.name][0], got[0]))
    return [t.name for t in tables], mismatches
