"""Administering cards: rename, close and reopen, never delete; and merchant corrections that replace.

Closing a card is "made redundant": all its data stays, it is greyed out in the UI and left out of pay dates and
recommendations. These tests pin the data-safety side of that: nothing is ever removed.
"""
import pytest

import cards
import database
from test_cards_accounts import MULTI, icici_clean, multi, upload  # noqa: F401  (fixtures and helpers)

API = "/spendlens/api"


def two_cards(client, monkeypatch):
    """One ICICI statement with a re-issued card (7000 -> 7018) and a second card (4005) on one bill."""
    upload(client, monkeypatch, {"multi.pdf": multi()})
    cs = {tuple(c["numbers"]): c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"}
    return cs[("7000", "7018")], cs[("4005",)]


def row_counts():
    db = database.get_db()
    try:
        return (db.execute("SELECT COUNT(*) FROM card_txns").fetchone()[0], db.execute("SELECT COUNT(*) FROM card_statements").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
    finally:
        db.close()


# ------------------------------------------------------------------ the admin list

def test_the_admin_list_shows_every_card_with_its_data(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    rows = {r["id"]: r for r in client.get(f"{API}/cards/admin").json()}
    r = rows[a["id"]]
    assert r["numbers"] == ["7000", "7018"] and r["status"] == "active" and r["scheme"] == "Usage only"
    assert r["transactions"] == 4 and r["spend"] == 2500.0 and r["since"] == "2021-04-05" and r["last_used"] == "2021-09-30"
    assert r["shared_with"] == [b["name"]], "the cards on one bill know about each other"


def test_the_sbi_card_is_in_the_list_too(client, seeded_db):
    names = [r["name"] for r in client.get(f"{API}/cards/admin").json()]
    assert "CASHBACK SBI Card" in names


# ------------------------------------------------------------------ rename

def test_rename(client, icici_clean, monkeypatch):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    r = client.patch(f"{API}/cards/{a['id']}", json={"name": "  My   travel card "})
    assert r.status_code == 200 and r.json()["name"] == "My travel card", "spaces are tidied"
    assert next(c for c in client.get(f"{API}/cards").json() if c["id"] == a["id"])["name"] == "My travel card"


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
def test_a_bad_name_is_refused_and_changes_nothing(client, icici_clean, monkeypatch, name):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    assert client.patch(f"{API}/cards/{a['id']}", json={"name": name}).status_code == 400
    assert next(c for c in client.get(f"{API}/cards").json() if c["id"] == a["id"])["name"] == a["name"]


# ------------------------------------------------------------------ close and reopen

def test_closing_a_card_closes_every_number_it_has_had_but_not_its_neighbour(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    assert client.patch(f"{API}/cards/{a['id']}", json={"status": "closed"}).json()["status"] == "closed"
    db = database.get_db()
    try:
        st = dict(db.execute("SELECT last4, status FROM cards WHERE issuer='ICICI Bank'").fetchall())
    finally:
        db.close()
    assert st["7000"] == st["7018"] == "closed", "the re-issued numbers are one card"
    assert st["4005"] == "active", "the other card on the bill is unaffected"


def test_a_closed_card_can_be_reopened(client, icici_clean, monkeypatch):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{a['id']}", json={"status": "closed"})
    assert client.patch(f"{API}/cards/{a['id']}", json={"status": "active"}).json()["status"] == "active"


def test_an_unknown_status_is_refused(client, icici_clean, monkeypatch):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    assert client.patch(f"{API}/cards/{a['id']}", json={"status": "deleted"}).status_code == 400


def test_closing_and_reopening_never_removes_a_row(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    before = row_counts()
    for body in ({"status": "closed"}, {"name": "Renamed"}, {"status": "active"}, {"status": "closed"}):
        client.patch(f"{API}/cards/{a['id']}", json=body)
    assert row_counts() == before, "transactions, statements and cards are all still there"


def test_there_is_no_way_to_delete_a_card(client, icici_clean, monkeypatch):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    before = row_counts()
    assert client.delete(f"{API}/cards/{a['id']}").status_code == 405
    assert row_counts() == before


def test_an_unknown_card_is_404(client, seeded_db):
    assert client.patch(f"{API}/cards/999999", json={"name": "x"}).status_code == 404


def test_closed_cards_are_listed_after_the_active_ones(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{b['id']}", json={"status": "closed"})
    order = [(r["id"], r["status"]) for r in client.get(f"{API}/cards/admin").json()]
    statuses = [s for _, s in order]
    assert statuses == sorted(statuses, key=lambda s: s == "closed"), "active first, then closed"
    assert order[-1] == (b["id"], "closed")


# ------------------------------------------------------------------ what closing changes elsewhere

def test_the_overview_marks_a_closed_card_and_puts_it_last(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{b['id']}", json={"status": "closed"})
    o = client.get(f"{API}/cards/overview").json()
    tile = next(t for t in o["cards"] if t["id"] == b["id"])
    assert tile["status"] == "closed" and o["cards"][-1]["id"] == b["id"]
    assert o["totals"]["active_cards"] == o["totals"]["cards"] - 1
    assert tile["spend"] == 2400.0, "its history still counts: only its look and its to-do items change"


def test_a_closed_card_with_no_bill_outstanding_is_not_on_the_pay_list(client, icici_clean, monkeypatch):  # noqa: F811
    """A single closed card has nothing to wait for. (Cards sharing a bill with an active card stay on that bill.)"""
    upload(client, monkeypatch, {"multi.pdf": multi()})
    cs = [c for c in client.get(f"{API}/cards").json() if c["issuer"] == "ICICI Bank"]
    for c in cs:
        client.patch(f"{API}/cards/{c['id']}", json={"status": "closed"})
    o = client.get(f"{API}/cards/overview").json()
    assert not any(n in cs_names for p in o["pay"] for n in p["cards"] for cs_names in [[c["name"] for c in cs]])


# ------------------------------------------------------------------ corrections replace, never stack

def test_a_merchant_correction_replaces_the_earlier_one(client, seeded_db):
    sbi = next(c for c in client.get(f"{API}/cards").json() if c["profile"] == "sbi_cashback")
    for cls in ("excluded", "online", "offline"):             # clicking through the dropdown
        assert client.post(f"{API}/cards/merchant-rule", json={"pattern": "ZZTESTSHOP", "cls": cls, "card_id": sbi["id"]}).status_code == 200
    rules = [r for r in client.get(f"{API}/cards/merchant-rules", params={"card_id": sbi["id"]}).json() if r["pattern"] == "ZZTESTSHOP"]
    try:
        assert len(rules) == 1 and rules[0]["cls"] == "offline", "one rule, the last choice: not three"
    finally:
        for r in rules:
            client.delete(f"{API}/cards/merchant-rules/{r['id']}")


def test_rules_for_different_merchants_do_not_replace_each_other(client, seeded_db):
    sbi = next(c for c in client.get(f"{API}/cards").json() if c["profile"] == "sbi_cashback")
    for pat in ("ZZONE", "ZZTWO"):
        client.post(f"{API}/cards/merchant-rule", json={"pattern": pat, "cls": "online", "card_id": sbi["id"]})
    rules = [r for r in client.get(f"{API}/cards/merchant-rules", params={"card_id": sbi["id"]}).json() if r["pattern"].startswith("ZZ")]
    try:
        assert {r["pattern"] for r in rules} == {"ZZONE", "ZZTWO"}
    finally:
        for r in rules:
            client.delete(f"{API}/cards/merchant-rules/{r['id']}")


# ------------------------------------------------------------------ adding a card by hand

def test_a_card_added_by_hand_appears_everywhere_with_no_data(client, seeded_db):
    r = client.post(f"{API}/cards", json={"name": "ZZ Test Magnus", "profile": "generic", "issuer": "Axis Bank", "last4": "9876"})
    assert r.status_code == 200 and r.json()["transactions"] == 0 and r.json()["numbers"] == ["9876"]
    cid = r.json()["id"]
    assert cid in [c["id"] for c in client.get(f"{API}/cards").json()], "it is on the Cards page"
    assert client.get(f"{API}/cards/dashboard", params={"card_id": cid}).status_code == 200
    assert client.get(f"{API}/cards/overview").status_code == 200 and client.get(f"{API}/cards/advice").status_code == 200


def test_a_scheme_card_takes_its_banks_name_and_a_duplicate_is_refused(client, seeded_db):
    r = client.post(f"{API}/cards", json={"name": "ZZ HDFC", "profile": "hdfc_neu", "last4": "6543"})
    assert r.status_code == 200
    again = client.post(f"{API}/cards", json={"name": "Again", "profile": "hdfc_neu", "last4": "6543"})
    assert again.status_code == 400 and "already here" in again.json()["detail"]


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "x", "profile": "nope"}, {"name": "x", "profile": "generic", "issuer": "B", "last4": "12"}])
def test_a_bad_new_card_is_refused(client, seeded_db, body):
    assert client.post(f"{API}/cards", json=body).status_code == 400


def test_a_placeholder_needs_only_a_name_and_two_make_two_cards(client, seeded_db):
    ids = []
    for n in ("ZZ Placeholder A", "ZZ Placeholder B"):
        r = client.post(f"{API}/cards", json={"name": n})
        assert r.status_code == 200 and r.json()["transactions"] == 0
        ids.append(r.json()["id"])
    assert ids[0] != ids[1], "a placeholder never attaches to another card of the same bank"
    names = [c["name"] for c in client.get(f"{API}/cards").json()]
    assert "ZZ Placeholder A" in names and "ZZ Placeholder B" in names


# ------------------------------------------------------------------ editing a card's details

def make(client, name, **kw):
    r = client.post(f"{API}/cards", json={"name": name, **kw})
    assert r.status_code == 200
    return r.json()


def test_every_detail_of_a_card_can_be_edited(client, seeded_db):
    c = make(client, "ZZ Meta A", profile="generic", issuer="Axis Bank", last4="1111")
    r = client.patch(f"{API}/cards/{c['id']}", json={
        "name": "ZZ Meta A2", "issuer": "Axis Bank Ltd", "last4": "2222", "network": "Visa", "notes": " travel card ",
        "credit_limit": 250000, "annual_fee": 1000, "fee_waiver_spend": 200000, "statement_day": 12, "grace_days": 18})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["name"], d["issuer"], d["numbers"], d["network"], d["notes"]) == ("ZZ Meta A2", "Axis Bank Ltd", ["2222"], "Visa", "travel card")
    assert (d["credit_limit"], d["annual_fee"], d["fee_waiver_spend"], d["statement_day"], d["grace_days"]) == (250000, 1000, 200000, 12, 18)
    assert d["cycle_verified"] is True, "a cycle you enter is one you have checked"


def test_a_partial_edit_leaves_the_rest_alone(client, seeded_db):
    c = make(client, "ZZ Meta B", issuer="Axis Bank", last4="3333")
    client.patch(f"{API}/cards/{c['id']}", json={"annual_fee": 500, "notes": "keep"})
    d = client.patch(f"{API}/cards/{c['id']}", json={"network": "Mastercard"}).json()
    assert (d["annual_fee"], d["notes"], d["network"], d["numbers"], d["issuer"]) == (500, "keep", "Mastercard", ["3333"], "Axis Bank")


@pytest.mark.parametrize("body", [{"statement_day": 0}, {"statement_day": 32}, {"grace_days": 99}, {"credit_limit": -1},
                                  {"profile": "nope"}, {"last4": "12"}, {"issuer": "  "}, {"name": "", "annual_fee": 5}])
def test_a_bad_edit_is_refused_and_changes_nothing(client, seeded_db, body):
    digits = f"{abs(hash(str(body))) % 9000 + 1000}"          # each run gets its own card
    c = make(client, f"ZZ Meta C{digits}", issuer="Axis Bank", last4=digits)
    assert client.patch(f"{API}/cards/{c['id']}", json={"annual_fee": 0, **body}).status_code == 400
    after = next(x for x in client.get(f"{API}/cards/admin").json() if x["id"] == c["id"])
    assert after["name"] == c["name"] and after["annual_fee"] == 0 and after["statement_day"] == c["statement_day"]


def test_two_cards_cannot_end_up_with_the_same_bank_and_digits(client, seeded_db):
    a = make(client, "ZZ Meta D1", issuer="Kotak Bank", last4="5555")
    b = make(client, "ZZ Meta D2", issuer="Kotak Bank", last4="6666")
    r = client.patch(f"{API}/cards/{b['id']}", json={"last4": "5555"})
    assert r.status_code == 400 and "already" in r.json()["detail"]
    assert client.patch(f"{API}/cards/{a['id']}", json={"last4": "5555"}).status_code == 200, "keeping its own digits is fine"


def test_changing_the_scheme_resets_its_rates_and_keeps_the_data(client, seeded_db):
    c = make(client, "ZZ Meta E", profile="generic", issuer="Axis Bank", last4="7777")
    d = client.patch(f"{API}/cards/{c['id']}", json={"profile": "sbi_cashback"}).json()
    assert d["profile"] == "sbi_cashback" and d["scheme"] == "SBI Cashback"
    assert client.get(f"{API}/cards/dashboard", params={"card_id": c["id"]}).status_code == 200


def test_editing_the_limit_and_fees_applies_to_every_number_of_one_card(client, icici_clean, monkeypatch):  # noqa: F811
    a, _ = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{a['id']}", json={"credit_limit": 123456, "annual_fee": 99})
    db = database.get_db()
    try:
        rows = db.execute("SELECT last4, credit_limit, annual_fee FROM cards WHERE last4 IN ('7000','7018')").fetchall()
    finally:
        db.close()
    assert len(rows) == 2 and all(r["credit_limit"] == 123456 and r["annual_fee"] == 99 for r in rows)


# ------------------------------------------------------------------ every card has its own colour

def colours(client):
    return {c["id"]: c["color"].lower() for c in client.get(f"{API}/cards").json()}


def test_no_two_cards_share_a_colour_however_many_there_are(client, seeded_db):
    for i in range(14):                                       # more than the palette holds
        make(client, f"ZZ Colour {i}", issuer="Colour Bank", last4=f"{7000 + i}")
    cs = colours(client)
    assert len(set(cs.values())) == len(cs), "every card has a different colour"
    assert all(c.startswith("#") and len(c) == 7 for c in cs.values())


def test_a_card_keeps_its_colour_when_others_change(client, seeded_db):
    a = make(client, "ZZ Keep A", issuer="Keep Bank", last4="8001")
    before = colours(client)
    b = make(client, "ZZ Keep B", issuer="Keep Bank", last4="8002")
    client.patch(f"{API}/cards/{b['id']}", json={"status": "closed"})
    client.patch(f"{API}/cards/{a['id']}", json={"color": "#010203"})
    after = colours(client)
    assert all(after[i] == before[i] for i in before if i != a["id"]), "choosing one colour moves no other card's"
    assert after[a["id"]] == "#010203"


def test_a_colour_you_choose_is_yours_but_never_a_duplicate(client, seeded_db):
    a = make(client, "ZZ Pick A", issuer="Pick Bank", last4="8101")
    b = make(client, "ZZ Pick B", issuer="Pick Bank", last4="8102")
    taken = colours(client)[a["id"]]
    r = client.patch(f"{API}/cards/{b['id']}", json={"color": taken})
    assert r.status_code == 400 and "already uses that colour" in r.json()["detail"]
    assert client.patch(f"{API}/cards/{a['id']}", json={"color": taken}).status_code == 200, "its own colour is fine"
    assert client.patch(f"{API}/cards/{b['id']}", json={"color": "#12ab34"}).json()["color"] == "#12ab34"
    assert client.patch(f"{API}/cards/{b['id']}", json={"color": "not-a-colour"}).status_code == 400


def test_the_overview_and_advice_use_the_same_colours(client, seeded_db):
    cs = colours(client)
    for t in client.get(f"{API}/cards/overview").json()["cards"]:
        assert t["color"].lower() == cs[t["id"]]
    for c in client.get(f"{API}/cards/advice").json()["cards"]:
        assert c["color"].lower() == cs[c["id"]]


# ------------------------------------------------------------------ dragging cards into an order

def test_a_dragged_order_is_kept_and_includes_closed_cards(client, icici_clean, monkeypatch):  # noqa: F811
    a, b = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{a['id']}", json={"status": "closed"})
    try:
        first = [c["id"] for c in client.get(f"{API}/cards").json()]
        flipped = list(reversed(first))
        assert client.put(f"{API}/cards/order", json={"ids": flipped}).json()["ids"] == flipped
        assert [c["id"] for c in client.get(f"{API}/cards").json()] == flipped
        assert [c["id"] for c in client.get(f"{API}/cards/overview").json()["cards"]] == flipped
    finally:                       # the database is shared by the whole run, so put it back
        client.patch(f"{API}/cards/{a['id']}", json={"status": "active"})
        db = database.get_db()
        try:
            db.execute("UPDATE cards SET sort_order=0")
            db.commit()
        finally:
            db.close()


def test_ordering_an_unknown_card_changes_nothing(client, icici_clean, monkeypatch):  # noqa: F811
    two_cards(client, monkeypatch)
    before = [c["id"] for c in client.get(f"{API}/cards").json()]
    assert client.put(f"{API}/cards/order", json={"ids": [999999]}).status_code == 404
    assert [c["id"] for c in client.get(f"{API}/cards").json()] == before
