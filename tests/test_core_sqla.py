"""Core helpers on SQLAlchemy, written to run on SQLite and Postgres alike."""
import re
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

BACKEND = Path(__file__).resolve().parent.parent / "spendlens"
STAMP = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")


def test_utc_now_text_matches_sqlite_datetime_now():
    from db.base import utc_now_text
    assert STAMP.match(utc_now_text())


def test_orm_created_expense_gets_the_old_created_at_format(client, seeded_db):
    cat = client.get("/spendlens/api/categories").json()[0]["id"]
    e = client.post("/spendlens/api/expenses", json={"category_id": cat, "date": "2026-10-03", "amount": 12, "note": "core-sqla stamp"}).json()
    try:
        assert STAMP.match(client.get(f"/spendlens/api/expenses/{e['id']}").json()["created_at"])
    finally:
        client.delete(f"/spendlens/api/expenses/{e['id']}")


def test_models_compile_for_postgres_without_sqlite_defaults():
    from db.models import Expense, Reminder, ReminderCategory, Subcategory, SubcategoryRule, Tracker, Vacation
    for model in (Expense, Reminder, ReminderCategory, Subcategory, SubcategoryRule, Tracker, Vacation):
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "datetime(" not in ddl, model.__name__


def test_apply_rules_maps_unmapped_notes_on_a_session(seeded_db):
    from db.engine import SessionLocal
    from db.models import Category, Expense, Subcategory, SubcategoryRule
    from subcategories import apply_rules, load_rules

    with SessionLocal() as s:
        cat = s.query(Category).order_by(Category.id).first()
        sub = Subcategory(category_id=cat.id, name="Core SQLA sub", sort_order=99)
        s.add(sub)
        s.flush()
        rule = SubcategoryRule(category_id=cat.id, pattern="zz-core-sqla", match_type="contains", subcategory_id=sub.id)
        hit = Expense(category_id=cat.id, date="2026-10-04", amount=5, note="paid ZZ-core-sqla twice")
        miss = Expense(category_id=cat.id, date="2026-10-04", amount=5, note="nothing to see")
        s.add_all([rule, hit, miss])
        s.flush()
        try:
            assert {"pattern": "zz-core-sqla", "match_type": "contains", "subcategory_id": sub.id} in load_rules(s, cat.id)
            assert apply_rules(s) >= 1
            s.refresh(hit)
            s.refresh(miss)
            assert hit.subcategory_id == sub.id and miss.subcategory_id is None
        finally:
            s.rollback()


def test_apply_rules_also_takes_a_connection(seeded_db):
    from db.engine import engine
    from subcategories import apply_rules
    with engine.connect() as conn:
        assert apply_rules(conn) >= 0
        conn.rollback()


def test_core_route_and_model_files_carry_no_sqlite_only_sql():
    files = ["routes/expense_routes.py", "routes/reminder_routes.py", "routes/tracker_routes.py",
             "db/models/expense.py", "db/models/reminders.py", "db/models/trackers.py"]
    for f in files:
        src = (BACKEND / f).read_text(encoding="utf-8")
        for bad in ("import sqlite3", "datetime('now')", "julianday(", "PRAGMA", "INSERT OR ", "get_db_dep", "func.strftime"):
            assert bad not in src, f"{bad!r} in {f}"
