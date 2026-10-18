"""The reminder calendar: categories, reminders, the month view, suggestions, settings and the .ics feed.

Each test builds its own categories/reminders and works with ids it created, so it does not depend on - or
disturb - anything else in the shared test database. Months are fixed (2021) so results never depend on today's
date; `today=` pins the clock where a state depends on it.
"""
import itertools
import os
import subprocess
import sys

import pytest

from conftest import ROOT

API = "/spendlens/api"
HEAD = "e6a8c1d4f9b3"  # latest Alembic revision; the migration tests upgrade a real-data copy to it
_n = itertools.count(1)


def new_cat(client, color="#112233"):
    r = client.post(f"{API}/reminder-categories", json={"name": f"ZZ Rem {next(_n)}", "color": color})
    assert r.status_code == 201, r.text
    return r.json()


def new_rem(client, cat_id, **kw):
    body = {"category_id": cat_id, "name": f"ZZ reminder {next(_n)}", "day": 5, "amount": 100}
    body.update(kw)
    r = client.post(f"{API}/reminders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def expense_cat(client, subs=("Alpha", "Beta")):
    cat = client.post(f"{API}/categories", json={"name": f"ZZ Rem Exp {next(_n)}", "start_month": "2020-01"}).json()
    made = [client.post(f"{API}/subcategories", json={"category_id": cat["id"], "name": s, "start_month": "2020-01"}).json() for s in subs]
    return cat, made


def spend(client, cat_id, date, amount=100, sub=None):
    r = client.post(f"{API}/expenses", json={"category_id": cat_id, "date": date, "amount": amount, "subcategory_id": sub})
    assert r.status_code in (200, 201), r.text


def calendar(client, month, today=None):
    params = {"month": month}
    if today:
        params["today"] = today
    r = client.get(f"{API}/reminders/calendar", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def occ(cal, key):
    found = [o for o in cal["occurrences"] if o["key"] == key]
    return found[0] if found else None


@pytest.fixture
def auto_rows(seeded_db):
    """Cards and SIP holdings the calendar reads on its own; removed afterwards."""
    from db.engine import SessionLocal
    from db.models import Card, Holding
    s = SessionLocal()
    cards = [
        Card(name="ZZ Fixed Card", statement_day=11, due_day=1, grace_days=20),
        Card(name="ZZ Estimated Card", statement_day=20, due_day=0, grace_days=20),
        Card(name="ZZ Closed Card", statement_day=5, due_day=2, status="closed"),
    ]
    holdings = [Holding(name=f"ZZ SIP {c}", sip_amount=1000 * (i + 1), sip_day=27) for i, c in enumerate("ABCDEF")]
    holdings.append(Holding(name="ZZ Solo SIP", sip_amount=2500, sip_day=29))
    holdings.append(Holding(name="ZZ No SIP day", sip_amount=999, sip_day=0))
    s.add_all(cards + holdings)
    s.commit()
    ids = {"fixed": cards[0].id, "est": cards[1].id, "closed": cards[2].id}
    yield ids
    for obj in cards + holdings:
        s.delete(s.merge(obj))
    s.commit()
    s.close()


def kinds(client):
    return {c["kind"]: c["id"] for c in client.get(f"{API}/reminder-categories").json() if c["kind"]}


# ---------------------------------------------------------------- categories

def test_default_categories_are_seeded(client, seeded_db):
    cats = {c["name"]: c for c in client.get(f"{API}/reminder-categories").json()}
    assert cats["Bills & EMI"]["kind"] is None and cats["Bills & EMI"]["color"] == "#f5b942"
    assert cats["Card dates"]["kind"] == "card" and cats["SIPs"]["kind"] == "sip"
    assert all("reminder_count" in c and "sort_order" in c for c in cats.values())


def test_category_create_update_and_validation(client, seeded_db):
    assert client.post(f"{API}/reminder-categories", json={"name": "  ", "color": "#ffffff"}).status_code == 400
    assert client.post(f"{API}/reminder-categories", json={"name": "x", "color": "red"}).status_code == 400
    cat = new_cat(client, "#ABCDEF")
    assert cat["color"] == "#abcdef" and cat["reminder_count"] == 0
    r = client.put(f"{API}/reminder-categories/{cat['id']}", json={"name": "  Renamed  ", "color": "#fff"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["color"] == "#fff"
    assert client.put(f"{API}/reminder-categories/{cat['id']}", json={"color": "nope"}).status_code == 400
    assert client.put(f"{API}/reminder-categories/999999", json={"name": "x"}).status_code == 404
    # card and SIP categories may be renamed and recoloured
    card = kinds(client)["card"]
    old = next(c for c in client.get(f"{API}/reminder-categories").json() if c["id"] == card)
    assert client.put(f"{API}/reminder-categories/{card}", json={"name": "Cards!"}).json()["name"] == "Cards!"
    client.put(f"{API}/reminder-categories/{card}", json={"name": old["name"]})


def test_category_delete_rules(client, seeded_db):
    assert client.delete(f"{API}/reminder-categories/{kinds(client)['card']}").status_code == 409
    assert client.delete(f"{API}/reminder-categories/{kinds(client)['sip']}").status_code == 409
    assert client.delete(f"{API}/reminder-categories/999999").status_code == 404

    cat, other = new_cat(client), new_cat(client)
    r1, r2 = new_rem(client, cat["id"]), new_rem(client, cat["id"])
    shown = next(c for c in client.get(f"{API}/reminder-categories").json() if c["id"] == cat["id"])
    assert shown["reminder_count"] == 2

    r = client.delete(f"{API}/reminder-categories/{cat['id']}")
    assert r.status_code == 409 and "move_to" in r.json()["detail"]
    assert client.delete(f"{API}/reminder-categories/{cat['id']}", params={"move_to": cat["id"]}).status_code == 409
    assert client.delete(f"{API}/reminder-categories/{cat['id']}", params={"move_to": 999999}).status_code == 409
    assert client.delete(f"{API}/reminder-categories/{cat['id']}", params={"move_to": other["id"], "delete_reminders": True}).status_code == 400

    r = client.delete(f"{API}/reminder-categories/{cat['id']}", params={"move_to": other["id"]})
    assert r.status_code == 200 and r.json()["moved"] == 2
    moved = {x["id"]: x for x in client.get(f"{API}/reminders").json()}
    assert moved[r1["id"]]["category_id"] == other["id"] and moved[r2["id"]]["category_id"] == other["id"]

    r = client.delete(f"{API}/reminder-categories/{other['id']}", params={"delete_reminders": True})
    assert r.status_code == 200 and r.json()["deleted_reminders"] == 2
    assert r1["id"] not in {x["id"] for x in client.get(f"{API}/reminders").json()}

    empty = new_cat(client)
    assert client.delete(f"{API}/reminder-categories/{empty['id']}").status_code == 200


# ---------------------------------------------------------------- reminders

def test_reminder_crud_and_validation(client, seeded_db):
    cat = new_cat(client)
    ecat, (alpha, beta) = expense_cat(client)
    other_cat, (other_sub, _) = expense_cat(client)

    r = new_rem(client, cat["id"], name="  Rent  ", amount=35000, day=1, note=" pay by 1st ")
    assert (r["name"], r["note"], r["repeat"], r["month"], r["enabled"]) == ("Rent", "pay by 1st", "monthly", None, True)
    assert set(r) == {"id", "category_id", "name", "amount", "day", "repeat", "month", "enabled", "note",
                      "expense_category_id", "expense_subcategory_id", "source_key"}

    def bad(**kw):
        body = {"category_id": cat["id"], "name": "x", "day": 5}
        body.update(kw)
        resp = client.post(f"{API}/reminders", json=body)
        assert resp.status_code == 400, (kw, resp.text)

    bad(name="   ")
    bad(day=0)
    bad(day=32)
    bad(amount=-1)
    bad(repeat="weekly")
    bad(repeat="yearly")                      # month missing
    bad(repeat="quarterly", month=13)
    bad(category_id=999999)
    bad(expense_category_id=999999)
    bad(expense_subcategory_id=alpha["id"])   # sub-category without its category
    bad(expense_category_id=ecat["id"], expense_subcategory_id=other_sub["id"])   # belongs elsewhere

    monthly = new_rem(client, cat["id"], repeat="monthly", month=7)
    assert monthly["month"] is None, "a monthly reminder has no month"
    linked = new_rem(client, cat["id"], expense_category_id=ecat["id"], expense_subcategory_id=alpha["id"], source_key=" 1:2 ")
    assert linked["source_key"] == "1:2"

    r = client.put(f"{API}/reminders/{linked['id']}", json={"amount": 5})
    assert r.status_code == 200 and r.json()["amount"] == 5 and r.json()["expense_subcategory_id"] == alpha["id"], "partial update keeps the rest"
    r = client.put(f"{API}/reminders/{linked['id']}", json={"expense_subcategory_id": None, "enabled": False})
    assert r.json()["expense_subcategory_id"] is None and r.json()["expense_category_id"] == ecat["id"] and r.json()["enabled"] is False
    assert client.put(f"{API}/reminders/{linked['id']}", json={"name": None}).status_code == 400
    assert client.put(f"{API}/reminders/{linked['id']}", json={"day": 40}).status_code == 400
    r = client.put(f"{API}/reminders/{linked['id']}", json={"repeat": "yearly", "month": 4})
    assert r.json()["repeat"] == "yearly" and r.json()["month"] == 4
    assert client.put(f"{API}/reminders/999999", json={"day": 3}).status_code == 404

    assert client.delete(f"{API}/reminders/{linked['id']}").status_code == 200
    assert client.delete(f"{API}/reminders/{linked['id']}").status_code == 404
    assert linked["id"] not in {x["id"] for x in client.get(f"{API}/reminders").json()}


def test_deleting_an_expense_category_or_subcategory_unlinks_reminders(client, seeded_db):
    cat = new_cat(client)
    ecat, (alpha, _) = expense_cat(client)
    r = new_rem(client, cat["id"], expense_category_id=ecat["id"], expense_subcategory_id=alpha["id"])
    assert client.delete(f"{API}/subcategories/{alpha['id']}").status_code == 200
    now = next(x for x in client.get(f"{API}/reminders").json() if x["id"] == r["id"])
    assert now["expense_subcategory_id"] is None and now["expense_category_id"] == ecat["id"]
    assert client.delete(f"{API}/categories/{ecat['id']}").status_code == 200
    now = next(x for x in client.get(f"{API}/reminders").json() if x["id"] == r["id"])
    assert now["expense_category_id"] is None


# ---------------------------------------------------------------- calendar

def test_calendar_states_and_repeats(client, seeded_db):
    cat = new_cat(client)
    ecat_a, (alpha, beta) = expense_cat(client)
    ecat_b, _ = expense_cat(client)
    spend(client, ecat_a["id"], "2021-03-20", sub=alpha["id"])

    done = new_rem(client, cat["id"], day=5, expense_category_id=ecat_a["id"])
    done_sub = new_rem(client, cat["id"], day=6, expense_category_id=ecat_a["id"], expense_subcategory_id=alpha["id"])
    wrong_sub = new_rem(client, cat["id"], day=7, expense_category_id=ecat_a["id"], expense_subcategory_id=beta["id"])
    watching = new_rem(client, cat["id"], day=10, expense_category_id=ecat_b["id"])
    plain = new_rem(client, cat["id"], day=20)
    quarterly = new_rem(client, cat["id"], day=8, repeat="quarterly", month=12)
    yearly_here = new_rem(client, cat["id"], day=9, repeat="yearly", month=3)
    yearly_not = new_rem(client, cat["id"], day=9, repeat="yearly", month=4)
    paused = new_rem(client, cat["id"], day=11, enabled=False)
    last = new_rem(client, cat["id"], day=31)

    early = calendar(client, "2021-03", today="2021-03-01")
    key = lambda r: f"r{r['id']}"
    assert occ(early, key(done))["state"] == "done" and occ(early, key(done_sub))["state"] == "done"
    assert occ(early, key(wrong_sub))["state"] == "up", "the right category but another sub-category is not a match"
    assert occ(early, key(watching))["state"] == "up" and occ(early, key(plain))["state"] == "up"
    assert occ(early, key(quarterly)) and occ(early, key(yearly_here))
    assert occ(early, key(yearly_not)) is None and occ(early, key(paused)) is None
    assert occ(early, key(last))["day"] == 31 and occ(early, key(done))["category_id"] == cat["id"]
    assert early["month"] == "2021-03" and early["today"] == "2021-03-01"
    assert 20 in early["logged_days"] and early["nudge"] == {"on": True, "time": "21:00"}

    late = calendar(client, "2021-03", today="2021-03-15")
    assert occ(late, key(wrong_sub))["state"] == "missing" and occ(late, key(watching))["state"] == "missing"
    assert occ(late, key(done))["state"] == "done"
    assert occ(late, key(plain))["state"] == "up", "20th is still ahead on the 15th"
    assert occ(calendar(client, "2021-03", today="2021-03-25"), key(plain))["state"] == "unlinked"

    april = calendar(client, "2021-04", today="2021-03-01")
    assert occ(april, key(quarterly)) is None and occ(april, key(yearly_here)) is None and occ(april, key(yearly_not))
    assert occ(calendar(client, "2021-06"), key(quarterly)), "every three months from December: March, June, September"

    feb = calendar(client, "2021-02", today="2021-01-01")
    assert occ(feb, key(last))["day"] == 28, "day 31 clamps to the last day of a short month"
    assert [o["day"] for o in late["occurrences"]] == sorted(o["day"] for o in late["occurrences"])
    assert client.get(f"{API}/reminders/calendar", params={"month": "2021-13"}).status_code == 400
    assert client.get(f"{API}/reminders/calendar", params={"today": "nope"}).status_code == 400


def test_calendar_occurrences_are_sorted_by_day_then_name(client, seeded_db):
    cat = new_cat(client)
    a, b, c = (new_rem(client, cat["id"], name=n, day=d) for n, d in (("Bravo", 4), ("Alpha", 4), ("Zulu", 2)))
    cal = calendar(client, "2021-03", today="2021-03-01")
    mine = [o["name"] for o in cal["occurrences"] if o["category_id"] == cat["id"]]
    assert mine == ["Zulu", "Alpha", "Bravo"]


def test_calendar_auto_card_and_sip_dates(client, seeded_db, auto_rows):
    k = kinds(client)
    mar = calendar(client, "2021-03", today="2021-03-05")
    fixed_due, fixed_stmt = occ(mar, f"card-{auto_rows['fixed']}-due"), occ(mar, f"card-{auto_rows['fixed']}-stmt")
    assert fixed_due["day"] == 1 and fixed_due["estimated"] is False and fixed_due["state"] == "unlinked"
    assert fixed_due["auto"] is True and fixed_due["reminder_id"] is None and fixed_due["category_id"] == k["card"]
    assert fixed_stmt["day"] == 11 and fixed_stmt["state"] == "info"
    assert occ(mar, f"card-{auto_rows['closed']}-due") is None and occ(mar, f"card-{auto_rows['closed']}-stmt") is None

    # statement on the 20th + 20 days: February's lands on 12 March, March's on 9 April
    est_mar = occ(mar, f"card-{auto_rows['est']}-due")
    assert est_mar["estimated"] is True and est_mar["day"] == 12 and "estimated" in est_mar["name"].lower()
    assert occ(mar, f"card-{auto_rows['est']}-stmt")["day"] == 20
    apr = calendar(client, "2021-04", today="2021-03-05")
    est_apr = occ(apr, f"card-{auto_rows['est']}-due")
    assert est_apr["day"] == 9 and est_apr["state"] == "up"

    sip = occ(mar, "sip-27")
    assert sip["name"] == "6 SIPs" and sip["amount"] == 21000 and sip["category_id"] == k["sip"] and sip["auto"] is True
    assert [ln.split(" ₹")[0] for ln in sip["note"].splitlines()] == [f"ZZ SIP {c}" for c in "ABCDEF"], "note is the full breakdown, no truncation"
    assert sum(int(ln.split(" ₹")[1].replace(",", "")) for ln in sip["note"].splitlines()) == 21000
    assert [x["name"] for x in sip["sources"]] == [f"ZZ SIP {c}" for c in "ABCDEF"], "sources lists every holding, not just the first four"
    assert all(x["day"] == 27 and x["amount"] > 0 and isinstance(x["holding_id"], int) for x in sip["sources"])
    solo = occ(calendar(client, "2021-02", today="2021-01-01"), "sip-29")
    assert solo["name"] == "ZZ Solo SIP" and solo["day"] == 28 and solo["amount"] == 2500, "SIP day 29 clamps in February"
    assert occ(mar, "sip-0") is None


# ---------------------------------------------------------------- suggestions

def shift(month, k):
    y, m = int(month[:4]), int(month[5:])
    idx = y * 12 + m - 1 + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def test_suggestions_detect_monthly_repeats(client, seeded_db):
    months = client.get(f"{API}/expenses/months").json()
    latest = months[0] if months else "2021-03"
    cat, (alpha, beta, gamma) = expense_cat(client, subs=("Alpha", "Beta", "Gamma"))
    for i, amount in enumerate([900, 1000, 1000, 1100, 1000, 1200]):
        spend(client, cat["id"], f"{shift(latest, -5 + i)}-15", amount=amount, sub=alpha["id"])
    for i in range(4):                      # only four months: not enough to call it monthly
        spend(client, cat["id"], f"{shift(latest, -3 + i)}-10", amount=50, sub=beta["id"])
    for i in range(6):                      # six months but three entries each: not once a month
        for d in (3, 12, 21):
            spend(client, cat["id"], f"{shift(latest, -5 + i)}-{d:02d}", amount=20, sub=gamma["id"])

    found = {s["key"]: s for s in client.get(f"{API}/reminders/suggestions").json()}
    s = found[f"{cat['id']}:{alpha['id']}"]
    assert s["name"] == "Alpha" and s["category_id"] == cat["id"] and s["subcategory_id"] == alpha["id"]
    assert (s["day"], s["amount"], s["min_amount"], s["max_amount"], s["months"]) == (15, 1000, 900, 1200, 6)
    assert s["last_seen"] == latest and 6 <= s["window"] <= 8
    assert f"{cat['id']}:{beta['id']}" not in found and f"{cat['id']}:{gamma['id']}" not in found

    rc = new_cat(client)
    new_rem(client, rc["id"], source_key=s["key"], expense_category_id=cat["id"], expense_subcategory_id=alpha["id"])
    assert s["key"] not in {x["key"] for x in client.get(f"{API}/reminders/suggestions").json()}, "a kept suggestion is not offered again"


# ---------------------------------------------------------------- settings

def test_settings(client, seeded_db):
    assert client.get(f"{API}/reminders/settings").json() == {"nudge_on": True, "nudge_time": "21:00"}
    try:
        r = client.put(f"{API}/reminders/settings", json={"nudge_time": "9:05"})
        assert r.status_code == 200 and r.json() == {"nudge_on": True, "nudge_time": "09:05"}
        for bad in ("25:00", "9:5", "abc", "12:60", ""):
            assert client.put(f"{API}/reminders/settings", json={"nudge_time": bad}).status_code == 400, bad
        assert client.put(f"{API}/reminders/settings", json={"nudge_on": False}).json() == {"nudge_on": False, "nudge_time": "09:05"}
        assert calendar(client, "2021-03")["nudge"] == {"on": False, "time": "09:05"}
    finally:
        client.put(f"{API}/reminders/settings", json={"nudge_on": True, "nudge_time": "21:00"})
    assert client.get(f"{API}/reminders/settings").json() == {"nudge_on": True, "nudge_time": "21:00"}


# ---------------------------------------------------------------- .ics

def feed(client, **params):
    params.setdefault("today", "2021-03-10")
    r = client.get(f"{API}/calendar.ics", params=params)
    assert r.status_code == 200, r.text
    return r


def events(text):
    """Unfolded VEVENT blocks, each a list of content lines."""
    lines = text.replace("\r\n ", "").split("\r\n")
    out, cur = [], None
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            cur = []
        elif ln == "END:VEVENT":
            out.append(cur)
            cur = None
        elif cur is not None:
            cur.append(ln)
    return out


def field(ev, name):
    return next((ln.split(":", 1)[1] for ln in ev if ln.startswith(name + ":") or ln.startswith(name + ";")), None)


def test_ics_structure_escaping_and_rules(client, seeded_db):
    cat = new_cat(client)
    long_name = "Quarterly property tax instalment ₹ " + "very long description " * 3
    rent = new_rem(client, cat["id"], name="Rent, flat; A", amount=176500, day=5, note="line one\nline two")
    last = new_rem(client, cat["id"], name=long_name.strip(), amount=0, day=31, repeat="quarterly", month=3)
    yearly = new_rem(client, cat["id"], name="Insurance", amount=12000, day=15, repeat="yearly", month=2)
    clamp = new_rem(client, cat["id"], name="Clamp", amount=1, day=30, repeat="yearly", month=2)
    paused = new_rem(client, cat["id"], name="Paused one", enabled=False)

    first = feed(client, types=str(cat["id"]))
    assert first.headers["content-type"] == "text/calendar; charset=utf-8"
    text = first.content.decode("utf-8")
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", ""), "CRLF line endings only"
    assert f"reminder-{paused['id']}@spendlens" not in text and "Paused one" not in text, "disabled reminders stay out"
    assert all(len(ln.encode("utf-8")) <= 75 for ln in text.split("\r\n")), "lines folded at 75 octets"
    assert any(ln.startswith(" ") for ln in text.split("\r\n")), "the long name was folded"
    for head in ("VERSION:2.0", "CALSCALE:GREGORIAN", "X-WR-CALNAME:SpendLens", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"):
        assert head in text
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") == 4 and text.count("BEGIN:VALARM") == text.count("END:VALARM") == 4
    assert "PRODID:" in text

    evs = {field(e, "UID"): e for e in events(text)}
    assert set(evs) == {f"reminder-{r['id']}@spendlens" for r in (rent, last, yearly, clamp)}, "disabled reminders and other categories are left out"

    e = evs[f"reminder-{rent['id']}@spendlens"]
    assert field(e, "SUMMARY") == "Rent\\, flat\\; A ₹1\\,76\\,500"
    assert field(e, "DESCRIPTION") == "line one\\nline two"
    assert field(e, "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=5"
    assert any(ln.startswith("DTSTART;VALUE=DATE:") and ln.endswith("05") for ln in e)
    assert "TRIGGER:PT9H" in e and field(e, "DTSTAMP").endswith("Z")

    e = evs[f"reminder-{last['id']}@spendlens"]
    assert field(e, "RRULE") == "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=28,29,30,31;BYSETPOS=-1"
    start = field(e, "DTSTART")
    assert int(start[4:6]) % 3 == 0, "starts in a month that belongs to the every-three-months-from-March cycle"
    assert field(evs[f"reminder-{last['id']}@spendlens"], "SUMMARY") == long_name.strip().replace(",", "\\,")
    assert field(evs[f"reminder-{yearly['id']}@spendlens"], "RRULE") == "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=15"
    assert field(evs[f"reminder-{clamp['id']}@spendlens"], "RRULE") == "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29,30;BYSETPOS=-1"

    second = feed(client, types=str(cat["id"])).content.decode("utf-8")
    assert {field(e, "UID") for e in events(second)} == set(evs), "UIDs are stable between fetches"


def test_ics_types_filter_and_nudge(client, seeded_db):
    a, b = new_cat(client), new_cat(client)
    ra, rb = new_rem(client, a["id"]), new_rem(client, b["id"])
    uid = lambda r: f"reminder-{r['id']}@spendlens"

    only_a = {field(e, "UID") for e in events(feed(client, types=str(a["id"])).text)}
    assert only_a == {uid(ra)}
    both = {field(e, "UID") for e in events(feed(client, types=f"{a['id']},{b['id']}").text)}
    assert both == {uid(ra), uid(rb)}
    assert events(feed(client, types="zzz,9999999").text) == [], "unknown types are ignored"

    log = events(feed(client, types="log").text)
    assert len(log) == 1
    ev = log[0]
    assert field(ev, "UID") == "log-nudge@spendlens" and field(ev, "RRULE") == "FREQ=DAILY"
    assert field(ev, "DURATION") == "PT15M" and field(ev, "DTSTART") == "20210310T210000", "floating local time, no Z, no TZID"
    assert "TRIGGER:PT0S" in ev and "Log today's expenses" in field(ev, "SUMMARY")

    everything = {field(e, "UID") for e in events(feed(client).text)}
    assert {uid(ra), uid(rb), "log-nudge@spendlens"} <= everything

    try:
        client.put(f"{API}/reminders/settings", json={"nudge_on": False})
        assert events(feed(client, types="log").text) == []
        assert "log-nudge@spendlens" not in {field(e, "UID") for e in events(feed(client).text)}
    finally:
        client.put(f"{API}/reminders/settings", json={"nudge_on": True, "nudge_time": "21:00"})


def test_ics_includes_card_and_sip_dates(client, seeded_db, auto_rows):
    k = kinds(client)
    evs = {field(e, "UID"): e for e in events(feed(client, types=f"{k['card']},{k['sip']}").text)}
    fixed_due = evs[f"card-{auto_rows['fixed']}-due@spendlens"]
    assert field(fixed_due, "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=1" and field(fixed_due, "SUMMARY") == "ZZ Fixed Card payment due"
    assert field(evs[f"card-{auto_rows['fixed']}-stmt@spendlens"], "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=11"
    est = evs[f"card-{auto_rows['est']}-due@spendlens"]
    assert "(estimated)" in field(est, "SUMMARY") and field(est, "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=12"
    assert f"card-{auto_rows['closed']}-due@spendlens" not in evs
    group = evs["sip-27@spendlens"]
    assert field(group, "SUMMARY") == "6 SIPs ₹21\\,000" and field(group, "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=27"
    assert field(evs["sip-29@spendlens"], "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=28,29;BYSETPOS=-1"
    assert not any(field(e, "UID") == "log-nudge@spendlens" for e in events(feed(client, types=str(k["card"])).text))


# ---------------------------------------------------------------- migration on a copy of the real database

def _run(code, db_path):
    env = dict(os.environ, SPENDLENS_DB=str(db_path))
    return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True)


def test_migration_upgrades_and_downgrades_a_copy_of_the_real_database(real_db_copy):
    pre = "import sys; sys.path.insert(0, 'spendlens')\nfrom alembic.config import Config\nfrom alembic import command\n" \
          "cfg = Config('alembic.ini'); cfg.set_main_option('script_location', 'alembic')\n"
    probe = ("from sqlalchemy import create_engine, inspect, text\nimport os\n"
             "e = create_engine('sqlite:///' + os.environ['SPENDLENS_DB'])\n"
             "t = set(inspect(e).get_table_names())\n"
             "with e.connect() as c:\n"
             "    v = c.execute(text('select version_num from alembic_version')).scalar()\n"
             "    n = c.execute(text('select count(*) from reminder_categories')).scalar() if 'reminder_categories' in t else -1\n"
             "cols = {c['name'] for c in inspect(e).get_columns('holdings')}\n"
             "print(v, 'reminders' in t, 'reminder_settings' in t, n, 'sip_reminder' in cols)\n")
    up = _run(pre + "command.upgrade(cfg, 'head')\n" + probe, real_db_copy)
    assert up.returncode == 0, up.stderr
    version, has_rem, has_set, seeded, has_col = up.stdout.split()
    assert version == HEAD and has_rem == has_set == has_col == "True" and int(seeded) >= 3

    down = _run(pre + "command.downgrade(cfg, '7fa60c624af4')\n" + probe.replace("select count(*) from reminder_categories", "select 0").replace("if 'reminder_categories' in t else -1", ""), real_db_copy)
    assert down.returncode == 0, down.stderr
    version, has_rem, has_set, _, has_col = down.stdout.split()
    assert version == "7fa60c624af4" and has_rem == has_set == has_col == "False"

    again = _run(pre + "command.upgrade(cfg, 'head')\n" + probe, real_db_copy)
    assert again.returncode == 0, again.stderr
    assert again.stdout.split()[0] == HEAD and int(again.stdout.split()[3]) >= 3 and again.stdout.split()[4] == "True"


def test_migration_hides_employer_pf_but_keeps_ppf_ssy_funds_and_rds(blank_db):
    """The one-time default: PF holdings other than PPF / Sukanya / SSY (e.g. 'PF Morgan Stanley') are hidden from reminders."""
    pre = "import sys; sys.path.insert(0, 'spendlens')\nfrom alembic.config import Config\nfrom alembic import command\n" \
          "cfg = Config('alembic.ini'); cfg.set_main_option('script_location', 'alembic')\n" \
          "import database; database.init_db()\n"
    seed = ("from sqlalchemy import create_engine, text\nimport os\n"
            "e = create_engine('sqlite:///' + os.environ['SPENDLENS_DB'])\n"
            "rows = [('PF Morgan Stanley', 'PF'), ('PF Deloitte Consulting', 'PF'), ('PPF', 'PF'), ('Sukanya Samriddhi', 'PF'),\n"
            "        ('My SSY account', 'PF'), ('Axis Small Cap Fund', 'MF'), ('RD - @7.25%', 'FD')]\n"
            "with e.begin() as c:\n"
            "    for n, t in rows:\n"
            "        c.execute(text('insert into holdings (name, asset_type, sip_amount, sip_day) values (:n, :t, 1000, 1)'), {'n': n, 't': t})\n")
    read = ("with e.connect() as c:\n"
            "    print(sorted((n, v) for n, v in c.execute(text('select name, sip_reminder from holdings'))))\n")
    run = _run(pre + "command.upgrade(cfg, 'b3d5e8a1c2f4')\n" + seed + "command.upgrade(cfg, 'head')\n" + read, blank_db)
    assert run.returncode == 0, run.stderr
    assert dict(eval(run.stdout.strip().splitlines()[-1])) == {
        "PF Morgan Stanley": 0, "PF Deloitte Consulting": 0, "PPF": 1, "Sukanya Samriddhi": 1,
        "My SSY account": 1, "Axis Small Cap Fund": 1, "RD - @7.25%": 1}


def test_fund_label_drops_the_folio():
    from routes.reminder_routes import _fund_label
    assert _fund_label("Axis Small Cap Fund (Folio: 910127264776)") == "Axis Small Cap Fund"
    assert _fund_label("Parag Parikh Flexi Cap Fund (folio 17871570)") == "Parag Parikh Flexi Cap Fund"
    assert _fund_label("PPF") == "PPF"
    assert _fund_label("RD - @7.25%") == "RD - @7.25%"


# ---------------------------------------------------------------- showing / hiding a SIP in reminders

def sip_ids(client):
    return {x["name"]: x["holding_id"] for x in client.get(f"{API}/reminders/sips").json()}


def test_sip_list_and_hiding_one_removes_it_from_calendar_and_feed(client, seeded_db, auto_rows):
    ids = sip_ids(client)
    assert "ZZ SIP B" in ids and "ZZ No SIP day" not in ids, "only holdings with a SIP day are listed"
    row = next(x for x in client.get(f"{API}/reminders/sips").json() if x["name"] == "ZZ SIP B")
    assert set(row) == {"holding_id", "name", "label", "amount", "day", "show"} and row["show"] is True and row["amount"] == 2000 and row["day"] == 27

    hide = client.put(f"{API}/reminders/sips/{ids['ZZ SIP B']}", json={"show": False})
    assert hide.status_code == 200 and hide.json()["show"] is False
    listed = client.get(f"{API}/reminders/sips").json()
    assert next(x for x in listed if x["name"] == "ZZ SIP B")["show"] is False, "hidden SIPs stay listed so they can be shown again"

    sip = occ(calendar(client, "2021-03", today="2021-03-05"), "sip-27")
    assert sip["name"] == "5 SIPs" and sip["amount"] == 19000
    assert "ZZ SIP B" not in [x["name"] for x in sip["sources"]] and "ZZ SIP B" not in sip["note"]
    k = kinds(client)
    evs = {field(e, "UID"): e for e in events(feed(client, types=str(k["sip"])).text)}
    assert field(evs["sip-27@spendlens"], "SUMMARY") == "5 SIPs ₹19\,000"

    show = client.put(f"{API}/reminders/sips/{ids['ZZ SIP B']}", json={"show": True})
    assert show.status_code == 200 and show.json()["show"] is True
    sip = occ(calendar(client, "2021-03", today="2021-03-05"), "sip-27")
    assert sip["name"] == "6 SIPs" and sip["amount"] == 21000


def test_hiding_every_sip_of_a_day_drops_the_occurrence_and_the_holding_is_untouched(client, seeded_db, auto_rows):
    ids = sip_ids(client)
    assert client.put(f"{API}/reminders/sips/{ids['ZZ Solo SIP']}", json={"show": False}).status_code == 200
    assert occ(calendar(client, "2021-02", today="2021-01-01"), "sip-29") is None
    held = next(h for h in client.get(f"{API}/holdings").json() if h["id"] == ids["ZZ Solo SIP"])
    assert held["sip_amount"] == 2500 and held["sip_day"] == 29, "Holdings keeps applying the SIP"
    assert "sip_reminder" not in held, "the flag does not leak into the holdings JSON"


def test_sip_visibility_validation(client, seeded_db, auto_rows):
    ids = sip_ids(client)
    assert client.put(f"{API}/reminders/sips/999999", json={"show": False}).status_code == 404
    from db.engine import SessionLocal
    from db.models import Holding
    s = SessionLocal()
    nosip = s.query(Holding).filter(Holding.name == "ZZ No SIP day").first().id
    s.close()
    assert client.put(f"{API}/reminders/sips/{nosip}", json={"show": False}).status_code == 404, "a holding without a SIP day has nothing to show"
    assert client.put(f"{API}/reminders/sips/{ids['ZZ SIP A']}", json={}).status_code == 422



# ---------------------------------------------------------------- holidays and vacations

def new_vac(client, **kw):
    body = {"name": f"ZZ Trip {next(_n)}", "start_date": "2031-05-10", "end_date": "2031-05-12", "color": "#0f8a8a"}
    body.update(kw)
    r = client.post(f"{API}/vacations", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_vacation_crud_and_validation(client, seeded_db):
    v = new_vac(client, name="  Goa trip  ", color="#AABBCC")
    assert v == {"id": v["id"], "name": "Goa trip", "start_date": "2031-05-10", "end_date": "2031-05-12", "color": "#aabbcc"}
    assert v in client.get(f"{API}/vacations").json()

    r = client.put(f"{API}/vacations/{v['id']}", json={"end_date": "2031-05-15"})
    assert r.status_code == 200 and r.json()["end_date"] == "2031-05-15" and r.json()["name"] == "Goa trip"
    assert client.put(f"{API}/vacations/{v['id']}", json={"name": "Goa"}).json()["start_date"] == "2031-05-10"

    base = {"name": "x", "start_date": "2031-05-10", "end_date": "2031-05-12", "color": "#0f8a8a"}
    for bad in ({"name": "   "}, {"start_date": "10/05/2031"}, {"end_date": "2031-02-30"}, {"end_date": "2031-05-09"},
                {"end_date": "2032-05-12"}, {"color": "teal"}, {"color": "#abc"}):
        r = client.post(f"{API}/vacations", json={**base, **bad})
        assert r.status_code == 400, (bad, r.text)
    r = client.put(f"{API}/vacations/{v['id']}", json={"start_date": "2031-06-01"})
    assert r.status_code == 400 and "end_date" in r.json()["detail"], "a partial update is checked against the stored dates"
    assert client.post(f"{API}/vacations", json={**base, "start_date": "2031-01-01", "end_date": "2032-01-02"}).status_code == 400, "366 days at most"
    assert client.post(f"{API}/vacations", json={**base, "start_date": "2032-01-01", "end_date": "2032-12-31"}).status_code == 201, "a 366-day leap year is allowed"

    assert client.delete(f"{API}/vacations/{v['id']}").json() == {"ok": True}
    assert client.delete(f"{API}/vacations/{v['id']}").status_code == 404
    assert client.put(f"{API}/vacations/{v['id']}", json={"name": "y"}).status_code == 404


def test_calendar_lists_india_and_us_public_holidays(client, seeded_db):
    def found(month):
        return {(h["date"], h["country"]): h for h in calendar(client, month)["holidays"]}

    oct26 = found("2026-10")
    assert ("2026-10-02", "IN") in oct26 and oct26[("2026-10-02", "IN")]["day"] == 2
    assert ("2026-10-12", "US") in oct26 and oct26[("2026-10-12", "US")]["name"].startswith("Columbus")
    assert all(d.startswith("2026-10") for d, _ in oct26)

    dec = found("2026-12")
    assert ("2026-12-25", "IN") in dec and ("2026-12-25", "US") in dec, "Christmas is a holiday in both countries"
    assert ("2026-01-26", "IN") in found("2026-01") and ("2026-07-04", "US") in found("2026-07")

    rows = calendar(client, "2026-12")["holidays"]
    assert rows == sorted(rows, key=lambda h: (h["date"], h["country"]))
    assert set(rows[0]) == {"date", "day", "country", "name"}
    assert [h["country"] for h in rows if h["date"] == "2026-12-25"] == ["IN", "US"]


def test_calendar_vacations_overlap_the_month_and_are_not_clipped(client, seeded_db):
    v = new_vac(client, name="ZZ Long trip", start_date="2032-03-28", end_date="2032-04-04", color="#123456")
    new_vac(client, name="ZZ Later trip", start_date="2032-06-01", end_date="2032-06-03")
    shape = {"id": v["id"], "name": "ZZ Long trip", "start_date": "2032-03-28", "end_date": "2032-04-04", "color": "#123456"}

    assert shape in calendar(client, "2032-03")["vacations"]
    assert shape in calendar(client, "2032-04")["vacations"], "the same, unclipped range in the second month"
    assert shape not in calendar(client, "2032-02")["vacations"] and shape not in calendar(client, "2032-05")["vacations"]
    assert "ZZ Later trip" not in [x["name"] for x in calendar(client, "2032-04")["vacations"]]
    assert {"occurrences", "logged_days", "nudge", "today", "month"} <= set(calendar(client, "2032-03"))

    client.delete(f"{API}/vacations/{v['id']}")
    assert shape not in calendar(client, "2032-03")["vacations"]


def test_ics_vacation_is_an_all_day_range_with_an_exclusive_end(client, seeded_db):
    v = new_vac(client, name="Goa, trip; fun", start_date="2033-12-30", end_date="2034-01-02")
    one = new_vac(client, name="ZZ One day", start_date="2033-02-28", end_date="2033-02-28")
    r = feed(client)
    assert r.headers["content-type"].startswith("text/calendar")
    evs = {field(e, "UID"): e for e in events(r.text)}
    ev = evs[f"vacation-{v['id']}@spendlens"]
    assert "DTSTART;VALUE=DATE:20331230" in ev and "DTEND;VALUE=DATE:20340103" in ev, "DTEND is the day after the last day"
    assert field(ev, "SUMMARY") == "Goa\\, trip\\; fun" and "TRANSP:TRANSPARENT" in ev
    assert not any(ln.startswith(("RRULE", "BEGIN:VALARM")) for ln in ev), "no repeat rule and no alarm"
    day = evs[f"vacation-{one['id']}@spendlens"]
    assert "DTSTART;VALUE=DATE:20330228" in day and "DTEND;VALUE=DATE:20330301" in day

    only_vac = [field(e, "UID") for e in events(feed(client, types="vacation").text)]
    assert f"vacation-{v['id']}@spendlens" in only_vac and all(u.startswith("vacation-") for u in only_vac)
    log_only = [field(e, "UID") for e in events(feed(client, types="log").text)]
    assert log_only and not any(u.startswith("vacation-") for u in log_only), "the types filter leaves vacations out"
    assert not events(feed(client, types="").text), "an empty selection has no events"


def test_holidays_are_not_in_the_feed(client, seeded_db):
    text = feed(client, today="2026-10-01").text
    assert "Gandhi" not in text and "Columbus" not in text


def test_vacations_migration_upgrades_and_downgrades_a_copy_of_the_real_database(real_db_copy):
    pre = "import sys; sys.path.insert(0, 'spendlens')\nfrom alembic.config import Config\nfrom alembic import command\n" \
          "cfg = Config('alembic.ini'); cfg.set_main_option('script_location', 'alembic')\n"
    probe = ("from sqlalchemy import create_engine, inspect, text\nimport os\n"
             "e = create_engine('sqlite:///' + os.environ['SPENDLENS_DB'])\n"
             "with e.connect() as c:\n"
             "    v = c.execute(text('select version_num from alembic_version')).scalar()\n"
             "print(v, 'vacations' in inspect(e).get_table_names())\n")
    up = _run(pre + "command.upgrade(cfg, 'head')\n" + probe, real_db_copy)
    assert up.returncode == 0, up.stderr
    assert up.stdout.split() == [HEAD, "True"]
    down = _run(pre + "command.downgrade(cfg, 'c4e6a9b2d7f1')\n" + probe, real_db_copy)
    assert down.returncode == 0, down.stderr
    assert down.stdout.split() == ["c4e6a9b2d7f1", "False"]
    again = _run(pre + "command.upgrade(cfg, 'head')\n" + probe, real_db_copy)
    assert again.returncode == 0, again.stderr
    assert again.stdout.split() == [HEAD, "True"]
