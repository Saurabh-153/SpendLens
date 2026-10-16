"""The expense write paths (cell entries, ranges, single expenses, review mapping, sub-category lifecycle).

Each test builds its own category so it does not depend on - or disturb - the seed data.
"""
import itertools

API = "/spendlens/api"
MONTH = "2021-03"
_n = itertools.count(1)


def make_category(client, subs=("Alpha", "Beta")):
    cat = client.post(f"{API}/categories", json={"name": f"ZZ Writes {next(_n)}", "start_month": "2020-01"}).json()
    made = [client.post(f"{API}/subcategories", json={"category_id": cat["id"], "name": s, "start_month": "2020-01"}).json() for s in subs]
    return cat, made


def expenses_of(client, cat_id, month=MONTH):
    return [e for e in client.get(f"{API}/expenses", params={"month": month}).json() if e["category_id"] == cat_id]


def cell(client, cat_id, date, entries):
    return client.put(f"{API}/expenses/cell-entries", json={"category_id": cat_id, "date": date, "entries": entries})


def test_cell_entries_insert_update_and_delete(client, seeded_db):
    cat, (alpha, beta) = make_category(client)
    day = f"{MONTH}-05"

    assert cell(client, cat["id"], day, [
        {"subcategory_id": alpha["id"], "amount": 100, "note": " one "},
        {"subcategory_id": beta["id"], "amount": 50, "note": ""},
    ]).status_code == 200
    rows = expenses_of(client, cat["id"])
    assert sorted((r["subcategory_id"], r["amount"], r["note"]) for r in rows) == sorted(
        [(alpha["id"], 100, "one"), (beta["id"], 50, "")]), "notes are trimmed, both lines stored"
    assert all(r["created_at"] for r in rows), "the database's own created_at default is kept"

    keep = next(r for r in rows if r["subcategory_id"] == alpha["id"])
    assert cell(client, cat["id"], day, [{"id": keep["id"], "subcategory_id": alpha["id"], "amount": 175, "note": "x"}]).status_code == 200
    rows = expenses_of(client, cat["id"])
    assert [(r["id"], r["amount"], r["note"]) for r in rows] == [(keep["id"], 175, "x")], "the other line was removed, this one updated in place"

    assert cell(client, cat["id"], day, []).status_code == 200
    assert expenses_of(client, cat["id"]) == []


def test_cell_entries_rejects_foreign_entries_and_wrong_subcategories(client, seeded_db):
    cat, (alpha, _) = make_category(client)
    other, (other_sub, _) = make_category(client)
    day = f"{MONTH}-06"
    cell(client, cat["id"], day, [{"subcategory_id": alpha["id"], "amount": 10}])
    mine = expenses_of(client, cat["id"])[0]

    r = cell(client, other["id"], day, [{"id": mine["id"], "amount": 5}])
    assert r.status_code == 400 and "does not belong" in r.json()["detail"]
    r = cell(client, cat["id"], day, [{"subcategory_id": other_sub["id"], "amount": 5}])
    assert r.status_code == 400 and "Sub-category" in r.json()["detail"]
    assert [e["amount"] for e in expenses_of(client, cat["id"])] == [10], "a rejected save changes nothing"


def test_range_replace_and_add(client, seeded_db):
    cat, (alpha, beta) = make_category(client)
    body = {"category_id": cat["id"], "month": MONTH, "start_day": 10, "end_day": 12, "amount": 20, "subcategory_id": alpha["id"]}

    r = client.post(f"{API}/expenses/range", json=body)
    assert r.status_code == 201 and r.json() == {"ok": True, "days": 3}
    client.post(f"{API}/expenses/range", json={**body, "subcategory_id": beta["id"], "amount": 7, "mode": "add"})
    assert len(expenses_of(client, cat["id"])) == 6

    # replacing with a sub-category only removes that sub-category's own entries
    client.post(f"{API}/expenses/range", json={**body, "amount": 33})
    rows = expenses_of(client, cat["id"])
    assert sorted(r["amount"] for r in rows if r["subcategory_id"] == alpha["id"]) == [33, 33, 33]
    assert sorted(r["amount"] for r in rows if r["subcategory_id"] == beta["id"]) == [7, 7, 7]

    # replacing without one clears the whole day cell
    client.post(f"{API}/expenses/range", json={**body, "subcategory_id": None, "amount": 1, "end_day": 10})
    assert [(r["date"], r["amount"]) for r in expenses_of(client, cat["id"]) if r["date"].endswith("-10")] == [(f"{MONTH}-10", 1)]

    assert client.post(f"{API}/expenses/range", json={**body, "amount": 0}).status_code == 400
    assert client.post(f"{API}/expenses/range", json={**body, "start_day": 9, "end_day": 3}).status_code == 400


def test_single_expense_create_update_delete(client, seeded_db):
    cat, (alpha, beta) = make_category(client)
    made = client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": f"{MONTH}-15", "amount": 42,
                                                 "note": "n", "subcategory_id": alpha["id"]})
    assert made.status_code == 201
    e = made.json()
    assert e["cat_name"] == cat["name"] and e["icon"] and e["color"] and e["created_at"] and e["cashback"] == 0

    assert client.get(f"{API}/expenses/{e['id']}").json()["amount"] == 42
    upd = client.put(f"{API}/expenses/{e['id']}", json={"category_id": cat["id"], "date": f"{MONTH}-16", "amount": 43,
                                                         "note": "m", "cashback": 2, "subcategory_id": beta["id"]}).json()
    assert (upd["date"], upd["amount"], upd["note"], upd["cashback"], upd["subcategory_id"]) == (f"{MONTH}-16", 43, "m", 2, beta["id"])
    assert client.put(f"{API}/expenses/9999999", json={"category_id": cat["id"], "date": f"{MONTH}-16", "amount": 1}).json() == {"error": "Not found"}

    assert client.delete(f"{API}/expenses/{e['id']}").json() == {"ok": True}
    assert client.get(f"{API}/expenses/{e['id']}").status_code == 404


def test_new_spend_needs_an_open_category_and_a_valid_subcategory(client, seeded_db):
    cat, (alpha, _) = make_category(client)
    other, (other_sub, _) = make_category(client)
    r = client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": "2019-05-01", "amount": 1})
    assert r.status_code == 400 and "not active" in r.json()["detail"], "the category starts in 2020-01"
    r = client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": f"{MONTH}-01", "amount": 1, "subcategory_id": other_sub["id"]})
    assert r.status_code == 400


def test_review_map_assigns_matching_notes_and_remembers_the_rule(client, seeded_db):
    cat, (alpha, beta) = make_category(client)
    for day, note in ((20, "Mystery  Item"), (21, "mystery item"), (22, "other")):
        client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": f"{MONTH}-{day}", "amount": 10, "note": note})
    pending = [g for g in client.get(f"{API}/subcategories/review").json() if g["category_id"] == cat["id"]]
    assert {(g["note"], g["count"]) for g in pending} == {("mystery item", 2), ("other", 1)}

    r = client.post(f"{API}/subcategories/review/map", json={"category_id": cat["id"], "note": "Mystery Item", "subcategory_id": alpha["id"]})
    assert r.json() == {"updated": 2}
    mapped = [e for e in expenses_of(client, cat["id"]) if e["subcategory_id"] == alpha["id"]]
    assert len(mapped) == 2
    left = [g for g in client.get(f"{API}/subcategories/review").json() if g["category_id"] == cat["id"]]
    assert [(g["note"], g["count"]) for g in left] == [("other", 1)]

    # a sub-category from another category is refused
    _, (foreign, _) = make_category(client)
    r = client.post(f"{API}/subcategories/review/map", json={"category_id": cat["id"], "note": "other", "subcategory_id": foreign["id"]})
    assert r.status_code == 400


def test_subcategory_rename_archive_restore_delete(client, seeded_db):
    cat, (alpha, beta) = make_category(client)
    client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": f"{MONTH}-02", "amount": 5, "subcategory_id": alpha["id"]})

    assert client.put(f"{API}/subcategories/{beta['id']}", json={"name": "Gamma"}).json()["name"] == "Gamma"
    assert client.put(f"{API}/subcategories/{beta['id']}", json={"name": "  "}).status_code == 400

    # used: cannot be deleted, can be archived (with a count of later months that still hold data)
    r = client.delete(f"{API}/subcategories/{alpha['id']}")
    assert r.status_code == 409 and "archive" in r.json()["detail"].lower()
    a = client.post(f"{API}/subcategories/{alpha['id']}/archive", json={"from_month": "2021-02"}).json()
    assert a["end_month"] == "2021-01" and a["months_with_data_after"] == 1 and a["status"] == "archived"
    assert client.post(f"{API}/subcategories/{alpha['id']}/archive", json={"from_month": "2020-01"}).status_code == 400
    assert client.post(f"{API}/subcategories/{alpha['id']}/restore").json()["end_month"] is None

    # unused: deleted for good
    assert client.delete(f"{API}/subcategories/{beta['id']}").json() == {"ok": True}
    assert client.delete(f"{API}/subcategories/{beta['id']}").status_code == 404


def test_category_archive_and_restore_report_later_months(client, seeded_db):
    cat, _ = make_category(client, subs=())
    client.post(f"{API}/expenses", json={"category_id": cat["id"], "date": f"{MONTH}-02", "amount": 5})
    a = client.post(f"{API}/categories/{cat['id']}/archive", json={"from_month": "2021-02"}).json()
    assert a["end_month"] == "2021-01" and a["months_with_data_after"] == 1 and a["has_data"] is True
    assert client.post(f"{API}/categories/{cat['id']}/restore").json()["end_month"] is None
