"""The cards domain on SQLAlchemy: write paths through the API and through a Session, and a guard that no
SQLite-only SQL comes back."""
import os
import re

import pytest
from sqlalchemy import text

import cards
from db.engine import SessionLocal
from test_cards_amex import _purge as purge_amex, workbook
from dbutil import test_db

API = "/spendlens/api"
ISSUER = "ZZ SQLA Bank"
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spendlens")
CARD_FILES = ["cards.py", "card_perks.py", "card_advisor.py", "card_float.py", "cards_amex.py", "cards_bob.py",
              "cards_hdfc.py", "cards_icici.py", os.path.join("routes", "card_routes.py")]


def _purge(s):
    ids = list(s.execute(text("SELECT id FROM cards WHERE issuer=:i"), {"i": ISSUER}).scalars())
    for i in ids:
        for t in ("card_txns", "card_statements", "card_merchant_rules", "card_perks"):
            s.execute(text(f"DELETE FROM {t} WHERE card_id=:id"), {"id": i})
        s.execute(text("DELETE FROM cards WHERE id=:id"), {"id": i})
    s.execute(text("DELETE FROM card_accounts WHERE issuer=:i AND id NOT IN (SELECT account_id FROM cards)"), {"i": ISSUER})
    s.commit()


@pytest.fixture
def session(seeded_db):
    with SessionLocal() as s:
        _purge(s)
        yield s
        s.rollback()
        _purge(s)


def _new(client, name="ZZ Card", last4="1111"):
    r = client.post(f"{API}/cards", json={"name": name, "profile": "generic", "last4": last4, "issuer": ISSUER})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_patch_and_order_through_the_api(client, session):
    a, b = _new(client, "ZZ Alpha", "1111"), _new(client, "ZZ Beta", "2222")
    assert a["issuer"] == ISSUER and a["numbers"] == ["1111"] and a["transactions"] == 0
    dup = client.post(f"{API}/cards", json={"name": "ZZ Again", "profile": "generic", "last4": "1111", "issuer": ISSUER})
    assert dup.status_code == 400 and "already here" in dup.json()["detail"]

    out = client.patch(f"{API}/cards/{a['id']}", json={"name": "  ZZ   Alpha 2 ", "credit_limit": 50000, "notes": "n",
                                                      "statement_day": 5, "grace_days": 18, "color": "#123abc"}).json()
    assert (out["name"], out["credit_limit"], out["notes"], out["statement_day"], out["grace_days"], out["cycle_verified"],
            out["color"]) == ("ZZ Alpha 2", 50000, "n", 5, 18, True, "#123abc")
    clash = client.patch(f"{API}/cards/{b['id']}", json={"color": "#123ABC"})
    assert clash.status_code == 400 and "already uses that colour" in clash.json()["detail"]
    assert client.patch(f"{API}/cards/999999", json={"name": "x"}).status_code == 404

    order = [c["id"] for c in client.get(f"{API}/cards").json()]
    order.remove(b["id"])
    order.insert(0, b["id"])
    assert client.put(f"{API}/cards/order", json={"ids": order}).json()["ids"][0] == b["id"]
    assert client.put(f"{API}/cards/order", json={"ids": [999999]}).status_code == 404


def test_settings_put_applies_to_the_account(client, session):
    a = _new(client)
    body = {"name": "ZZ Renamed", "profile": "sbi_cashback", "rates": {"online": 4}, "statement_day": 9, "grace_days": 21,
            "pay_buffer_days": 2, "float_rate": 6, "credit_limit": 1000, "annual_fee": 10, "fee_waiver_spend": 20, "cashback_cap": 30}
    assert client.put(f"{API}/cards/{a['id']}", json=body).json() == {"ok": True}
    row = session.execute(text("SELECT name, profile, rates, statement_day, grace_days, cycle_verified, cashback_cap FROM cards WHERE id=:id"),
                          {"id": a["id"]}).mappings().one()
    assert (row["name"], row["profile"], row["statement_day"], row["grace_days"], row["cycle_verified"], row["cashback_cap"]) == \
           ("ZZ Renamed", "sbi_cashback", 9, 21, 1, 30)
    assert '"online": 4' in row["rates"]
    assert client.put(f"{API}/cards/999999", json=body).status_code == 404


def test_merchant_rules_reclassify_history(client, amex_clean):
    from test_cards_amex import _send
    _send(client, workbook())
    c = next(c for c in client.get(f"{API}/cards").json() if c["issuer"] == "American Express")
    for _ in range(2):    # the Amex scheme has one class; a repeat correction must replace, not stack
        assert client.post(f"{API}/cards/merchant-rule", json={"pattern": " zomato ", "cls": "other", "card_id": c["id"]}).json() == {"ok": True}
    rules = [r for r in client.get(f"{API}/cards/merchant-rules", params={"card_id": c["id"]}).json() if r["pattern"] == "ZOMATO"]
    assert [r["cls"] for r in rules] == ["other"], "a new correction replaces the old one"
    txns = client.get(f"{API}/cards/transactions", params={"card_id": c["id"], "limit": 50}).json()
    assert {t["cls"] for t in txns if "ZOMATO" in t["merchant"].upper()} == {"other"}
    assert all("period_to" in t for t in txns)
    assert client.delete(f"{API}/cards/merchant-rules/{rules[0]['id']}").json() == {"ok": True}
    assert client.delete(f"{API}/cards/merchant-rules/{rules[0]['id']}").status_code == 404
    bad = client.post(f"{API}/cards/merchant-rule", json={"pattern": "X", "cls": "excluded", "card_id": c["id"]})
    assert bad.status_code == 400 and "one of: other" in bad.json()["detail"]


@pytest.fixture
def amex_clean(seeded_db):
    db = test_db()
    purge_amex(db)
    db.close()
    yield
    db = test_db()
    purge_amex(db)
    db.close()


def test_perks_add_update_delete(client, session):
    a = _new(client)
    listed = client.get(f"{API}/cards/{a['id']}/perks").json()
    assert listed["perks"] == [] and listed["value_yr"] == 0, "a generic card seeds nothing"
    after = client.post(f"{API}/cards/{a['id']}/perks", json={"title": "  Lounge   access ", "value_yr": 1200}).json()
    p = after["perks"][0]
    assert (p["title"], p["value_yr"], p["checked"], p["sort"]) == ("Lounge access", 1200.0, True, 0)
    second = client.post(f"{API}/cards/{a['id']}/perks", json={"title": "Second"}).json()["perks"]
    assert [x["sort"] for x in second] == [0, 1]
    upd = client.patch(f"{API}/cards/perks/{p['id']}", json={"detail": "domestic", "checked": False}).json()
    assert next(x for x in upd["perks"] if x["id"] == p["id"])["checked"] is False
    assert client.patch(f"{API}/cards/perks/{p['id']}", json={"title": ""}).status_code == 400
    gone = client.delete(f"{API}/cards/perks/{p['id']}").json()
    assert [x["title"] for x in gone["perks"]] == ["Second"]
    assert client.delete(f"{API}/cards/perks/{p['id']}").status_code == 404
    assert client.post(f"{API}/cards/999999/perks", json={"title": "x"}).status_code == 404


def test_a_failed_import_leaves_nothing_behind(session):
    card = cards.create_card(session, "ZZ Import", "generic", "3333", ISSUER)
    before = session.execute(text("SELECT COUNT(*) FROM card_txns")).scalar_one()
    bad = cards.import_files(session, card["id"], [("junk.pdf", __import__("io").BytesIO(b"not a pdf"))])
    assert bad[0]["ok"] is False and "not a readable PDF" in bad[0]["error"]
    assert session.execute(text("SELECT COUNT(*) FROM card_txns")).scalar_one() == before


def test_a_card_without_spend_sorts_first_on_its_account(session):
    """account_cards orders by first spend with NULLS FIRST, which SQLite and PostgreSQL then agree on."""
    a = cards.create_card(session, "ZZ Old", "generic", "4444", ISSUER)
    b = cards.create_card(session, "ZZ New", "generic", "5555", ISSUER)
    cards.link_accounts(session, a["members"] + b["members"])
    session.execute(text("""INSERT INTO card_txns (card_id, row_hash, tx_date, amount, is_spend)
                            VALUES (:id, 'zz-sqla-1', '2024-01-01', 10, 1)"""), {"id": a["members"][0]})
    acct = cards.get_card(session, a["members"][0])["account_id"]
    assert [c["id"] for c in cards.account_cards(session, acct)] == [b["members"][0], a["members"][0]]
    session.rollback()


def test_card_code_has_no_sqlite_only_sql():
    banned = [r"\bsqlite3\b", r"\bget_db(_dep)?\b", r"\.lastrowid\b", r"\bINSERT\s+OR\b", r"\bstrftime\(", r"\bjulianday\(",
              r"datetime\('now'\)", r"\bPRAGMA\b", r"\.execute\(\s*f?\"[^\"]*\?", r"fetchone\(\)\[", r'",".join\("\?"']
    for f in CARD_FILES:
        src = open(os.path.join(BACKEND, f), encoding="utf-8").read()
        for pat in banned:
            hit = re.search(pat, src)
            assert not hit, f"{f}: {pat} at ...{src[max(0, hit.start() - 40):hit.end() + 40]}..."
