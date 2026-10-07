"""The migration chain: applied once, idempotent, and safe on the real schema."""
import sqlite3

import database


def connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_versions_are_unique_and_ordered():
    versions = [m[0] for m in database.MIGRATIONS]
    assert versions == sorted(versions), "migrations must be in ascending order"
    assert len(versions) == len(set(versions)), "duplicate migration version"


def test_seeded_db_is_fully_migrated(seeded_db):
    conn = connect(seeded_db)
    assert database.schema_version(conn) == database.MIGRATIONS[-1][0]
    assert database.pending_migrations(conn) == []


def test_running_twice_applies_nothing_the_second_time(unmigrated_db):
    conn = connect(unmigrated_db)
    first = database.run_migrations(conn)
    assert first, "a pre-migration database should have pending steps"
    assert database.run_migrations(conn) == [], "migrations are not idempotent"


def test_dead_tables_are_gone(unmigrated_db):
    conn = connect(unmigrated_db)
    database.run_migrations(conn)
    assert not ({"users", "rebalance_targets", "price_alerts"} & tables(conn))


def test_user_id_added_to_owned_tables(unmigrated_db):
    conn = connect(unmigrated_db)
    database.run_migrations(conn)
    for t in ("categories", "holdings", "transactions", "portfolio_goals"):
        assert "user_id" in database._columns(conn, t), f"{t} has no user_id"
        rows = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id IS NOT 1").fetchone()[0]
        assert rows == 0, f"{t} has rows not owned by user 1"


def test_migration_takes_a_backup_of_a_database_with_data(unmigrated_db):
    database.run_migrations(connect(unmigrated_db))
    backups = list(unmigrated_db.parent.glob("*.bak"))
    assert backups, "no backup was taken before migrating a database with data"


def test_expense_rows_survive_migration(unmigrated_db):
    conn = connect(unmigrated_db)
    before = conn.execute("SELECT COUNT(*), ROUND(SUM(amount), 2) FROM expenses").fetchone()
    database.run_migrations(conn)
    after = conn.execute("SELECT COUNT(*), ROUND(SUM(amount), 2) FROM expenses").fetchone()
    assert tuple(before) == tuple(after), "migrating changed the expense data"


def test_a_deleted_starter_category_stays_deleted_after_a_restart(tmp_path, monkeypatch):
    """Starting the app must not put back a category you deleted (the starter list is for a new database only)."""
    path = tmp_path / "restart.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database.init_db()
    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE name='Children / Baby'").fetchone()[0] == 1
    conn.execute("DELETE FROM category_targets WHERE category_id=12")
    conn.execute("DELETE FROM expenses WHERE category_id=12")
    conn.execute("DELETE FROM categories WHERE id=12")
    conn.commit()
    conn.close()
    database.init_db()                                   # a restart
    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM categories WHERE name='Children / Baby'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 18, "the others are untouched"


def test_deleted_starter_expenses_do_not_come_back_either(tmp_path, monkeypatch):
    path = tmp_path / "restart2.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    database.init_db()
    conn = connect(path)
    n = conn.execute("SELECT COUNT(*) FROM expenses WHERE date LIKE '2025-02-%'").fetchone()[0]
    assert n > 0
    conn.execute("DELETE FROM expenses WHERE date LIKE '2025-02-%'")
    conn.commit()
    conn.close()
    database.init_db()
    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM expenses WHERE date LIKE '2025-02-%'").fetchone()[0] == 0
