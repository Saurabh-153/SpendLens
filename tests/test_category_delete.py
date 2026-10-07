"""Deleting a category: never with expenses, and the dialog's numbers say what is at stake."""
import database

API = "/spendlens/api"


def counts():
    db = database.get_db()
    try:
        return (db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], db.execute("SELECT COUNT(*) FROM categories").fetchone()[0])
    finally:
        db.close()


def a_category_with_entries(client):
    for c in client.get(f"{API}/categories").json():
        if c["has_data"]:
            return c
    raise AssertionError("the fixture should have a category with entries")


def test_a_category_with_expenses_cannot_be_deleted_and_nothing_changes(client, seeded_db):
    c = a_category_with_entries(client)
    before = counts()
    r = client.delete(f"{API}/categories/{c['id']}")
    assert r.status_code == 409 and "archive" in r.json()["detail"].lower()
    assert counts() == before, "no expense and no category was removed"


def test_usage_reports_the_entries_the_dialog_will_show(client, seeded_db):
    c = a_category_with_entries(client)
    u = client.get(f"{API}/categories/{c['id']}/usage").json()
    assert u["entries"] > 0 and u["total"] > 0 and u["months"] >= 1 and u["can_delete"] is False
    assert u["first"] <= u["last"]
    db = database.get_db()
    try:
        assert u["entries"] == db.execute("SELECT COUNT(*) FROM expenses WHERE category_id=?", (c["id"],)).fetchone()[0]
    finally:
        db.close()


def test_an_unused_category_with_sub_categories_deletes_cleanly(client, seeded_db):
    made = client.post(f"{API}/categories", json={"name": "ZZ Delete Me", "icon": "🧪", "color": "#112233", "hint": "", "start_month": "2020-01", "target_pct": 0}).json()
    sub = client.post(f"{API}/subcategories", json={"category_id": made["id"], "name": "ZZ sub"})
    assert sub.status_code == 201, sub.text           # it really has a sub-category, which used to block the delete
    u = client.get(f"{API}/categories/{made['id']}/usage").json()
    assert u["entries"] == 0 and u["can_delete"] is True
    assert client.delete(f"{API}/categories/{made['id']}").status_code == 200, sub.text
    assert client.get(f"{API}/categories/{made['id']}/usage").status_code == 404
    db = database.get_db()
    try:
        assert db.execute("SELECT COUNT(*) FROM subcategories WHERE category_id=?", (made["id"],)).fetchone()[0] == 0, "no orphaned sub-categories"
    finally:
        db.close()


def test_usage_of_an_unknown_category_is_404(client, seeded_db):
    assert client.get(f"{API}/categories/999999/usage").status_code == 404
