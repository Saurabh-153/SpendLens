"""Day trackers on the reminder calendar (CRUD, ticking, month KPIs) and drag-to-move reminders.

Months are fixed in the past (2021) and `today=` pins the clock, so nothing depends on the real date. Each test works
only with the trackers, reminders and expense categories it creates.
"""
import itertools

from test_reminders import API, calendar, expense_cat, new_cat, new_rem, occ, spend

_n = itertools.count(1)


def new_tracker(client, **kw):
    body = {"name": f"ZZ Tracker {next(_n)}", "color": "#7a52d6", "target_per_week": 4}
    body.update(kw)
    r = client.post(f"{API}/trackers", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def tick(client, tid, day, done=True, today="2021-12-31"):
    r = client.put(f"{API}/trackers/{tid}/days/{day}", params={"today": today}, json={"done": done})
    assert r.status_code == 200, r.text
    return r.json()


def tracker_in(cal, tid):
    found = [t for t in cal["trackers"] if t["id"] == tid]
    assert found, "tracker missing from the calendar"
    return found[0]


# ---------------------------------------------------------------- CRUD and validation

def test_tracker_crud_defaults_and_validation(client):
    t = new_tracker(client, name="  Gym  ", weekdays=[4, 0, 0, 2])
    assert t["name"] == "Gym" and t["weekdays"] == [0, 2, 4] and t["pause_on"] == ["vacation"]
    assert t["bill_reminder_id"] is None and t["cost_links"] == []
    assert set(t) == {"id", "name", "color", "target_per_week", "weekdays", "pause_on", "bill_reminder_id", "cost_links", "sort_order"}
    plain = new_tracker(client)
    assert plain["weekdays"] == [0, 1, 2, 3, 4, 5, 6]

    for bad in ({"name": "  "}, {"color": "purple"}, {"target_per_week": 0}, {"target_per_week": 8}, {"weekdays": []},
                {"weekdays": [7]}, {"pause_on": ["school"]}, {"bill_reminder_id": 999999},
                {"cost_links": [{"category_id": 999999}]}):
        r = client.post(f"{API}/trackers", json={"name": "x", **bad})
        assert r.status_code == 400, (bad, r.text)
    ecat, (alpha, _) = expense_cat(client)
    other, (gamma, _) = expense_cat(client, subs=("Gamma", "Delta"))
    r = client.post(f"{API}/trackers", json={"name": "x", "cost_links": [{"category_id": ecat["id"], "subcategory_id": gamma["id"]}]})
    assert r.status_code == 400 and "does not belong" in r.json()["detail"]

    links = [{"category_id": ecat["id"], "subcategory_id": alpha["id"]}, {"category_id": other["id"]},
             {"category_id": other["id"]}]
    u = client.put(f"{API}/trackers/{t['id']}", json={"pause_on": ["US", "vacation", "US"], "target_per_week": 2, "cost_links": links}).json()
    assert u["pause_on"] == ["vacation", "US"] and u["target_per_week"] == 2 and u["name"] == "Gym"
    assert u["cost_links"] == [{"category_id": ecat["id"], "subcategory_id": alpha["id"]}, {"category_id": other["id"], "subcategory_id": None}], \
        "duplicates are dropped"
    assert client.put(f"{API}/trackers/{t['id']}", json={"name": None}).status_code == 400
    assert client.put(f"{API}/trackers/{t['id']}", json={"cost_links": []}).json()["cost_links"] == [], "cost_links replaces the list"
    assert client.put(f"{API}/trackers/999999", json={"name": "x"}).status_code == 404

    assert client.delete(f"{API}/trackers/{plain['id']}").json() == {"ok": True}
    assert client.delete(f"{API}/trackers/{plain['id']}").status_code == 404
    assert all(x["id"] != plain["id"] for x in client.get(f"{API}/trackers").json())


def test_reorder(client):
    a, b, c = new_tracker(client), new_tracker(client), new_tracker(client)
    out = client.put(f"{API}/trackers/reorder", json={"ids": [c["id"], a["id"]]}).json()
    ids = [t["id"] for t in out]
    assert ids[:2] == [c["id"], a["id"]] and ids.index(b["id"]) > 1, "listed first, the rest keep their order after"
    assert [t["id"] for t in client.get(f"{API}/trackers").json()] == ids
    assert client.put(f"{API}/trackers/reorder", json={"ids": [a["id"], a["id"]]}).status_code == 400
    assert client.put(f"{API}/trackers/reorder", json={"ids": [999999]}).status_code == 400


def test_ticking_is_idempotent_and_rejects_future_days(client):
    t = new_tracker(client)
    assert tick(client, t["id"], "2021-03-05") == {"tracker_id": t["id"], "date": "2021-03-05", "done": True}
    tick(client, t["id"], "2021-03-05")
    assert tracker_in(calendar(client, "2021-03", today="2021-03-31"), t["id"])["done_days"] == [5]
    tick(client, t["id"], "2021-03-05", done=False)
    tick(client, t["id"], "2021-03-05", done=False)
    assert tracker_in(calendar(client, "2021-03", today="2021-03-31"), t["id"])["done_days"] == []

    r = client.put(f"{API}/trackers/{t['id']}/days/2021-03-06", params={"today": "2021-03-05"}, json={"done": True})
    assert r.status_code == 400 and "future" in r.json()["detail"]
    assert client.put(f"{API}/trackers/{t['id']}/days/2021-02-30", json={"done": True}).status_code == 400
    assert client.put(f"{API}/trackers/{t['id']}/days/5-3-2021", json={"done": True}).status_code == 400
    assert client.put(f"{API}/trackers/999999/days/2021-03-05", json={"done": True}).status_code == 404


# ---------------------------------------------------------------- KPIs

def test_month_kpis(client):
    """March 2021 starts on a Monday: weeks are 1-7, 8-14, 15-21, 22-28 and a 3-day week 29-31. Today is Wed 24th."""
    bill = new_rem(client, new_cat(client)["id"], name="Gym membership", amount=2500, day=1)
    t = new_tracker(client, target_per_week=4, pause_on=[], bill_reminder_id=bill["id"])
    for d in (1, 2, 3, 4, 8, 9, 15, 16, 17, 18, 19, 22):
        tick(client, t["id"], f"2021-03-{d:02d}")
    tr = tracker_in(calendar(client, "2021-03", today="2021-03-24"), t["id"])
    assert tr["done_days"] == [1, 2, 3, 4, 8, 9, 15, 16, 17, 18, 19, 22] and tr["scheduled_days"] == list(range(1, 32))
    k = tr["kpi"]
    assert k["per_week"] == [{"start_day": 1, "end_day": 7, "done": 4, "goal": 4}, {"start_day": 8, "end_day": 14, "done": 2, "goal": 4},
                             {"start_day": 15, "end_day": 21, "done": 5, "goal": 4}, {"start_day": 22, "end_day": 28, "done": 1, "goal": 4},
                             {"start_day": 29, "end_day": 31, "done": 0, "goal": 2}], "4 x 3/7 = 1.71 rounds to 2"
    assert k["count"] == 12 and k["month_goal"] == 18
    assert k["expected_by_today"] == 13.71, "12 for three full weeks + 4 x 3/7 for Mon-Wed of week 4"
    assert k["status"] == "warn", "12 / 13.71 = 0.875"
    assert k["projected"] == 16, "12 ticks over 24 elapsed days -> 15.5 over 31, rounded half up"
    assert k["this_week"] == {"done": 1, "goal": 4}
    assert (k["complete_weeks"], k["weeks_on_target"], k["week_streak"]) == (3, 2, 1), "weeks 1 and 3 on target, week 2 missed"
    assert k["cost"] is None
    assert k["cost_per_visit"] == {"bill_name": "Gym membership", "amount": 2500, "per_visit": 208}

    past = tracker_in(calendar(client, "2021-03", today="2021-06-01"), t["id"])["kpi"]
    assert past["complete_weeks"] == 5 and past["this_week"] == {"done": 0, "goal": 2}, "a past month: every week is complete"
    assert past["expected_by_today"] == 18 and past["week_streak"] == 0, "the last week (0 of 2) breaks the streak"
    future = tracker_in(calendar(client, "2021-03", today="2021-02-01"), t["id"])["kpi"]
    assert future["complete_weeks"] == 0 and future["expected_by_today"] == 0 and future["status"] == "good"
    assert future["projected"] == 12 and future["this_week"] == {"done": 4, "goal": 4}, "a future month: no days elapsed, first week"

    client.put(f"{API}/reminders/{bill['id']}", json={"enabled": False})
    assert tracker_in(calendar(client, "2021-03", today="2021-03-24"), t["id"])["kpi"]["cost_per_visit"] is None
    client.put(f"{API}/reminders/{bill['id']}", json={"enabled": True})
    client.delete(f"{API}/reminders/{bill['id']}")
    assert next(x for x in client.get(f"{API}/trackers").json() if x["id"] == t["id"])["bill_reminder_id"] is None, \
        "deleting the bill unlinks it"


def test_status_good_and_bad(client):
    good = new_tracker(client, target_per_week=1, pause_on=[])
    tick(client, good["id"], "2021-03-01")
    assert tracker_in(calendar(client, "2021-03", today="2021-03-07"), good["id"])["kpi"]["status"] == "good"
    bad = new_tracker(client, target_per_week=7, pause_on=[])
    tick(client, bad["id"], "2021-03-01")
    assert tracker_in(calendar(client, "2021-03", today="2021-03-07"), bad["id"])["kpi"]["status"] == "bad"


def test_holidays_and_vacations_lower_the_goal(client):
    # US Memorial Day is Monday 31 May 2021; India's Republic Day is Tuesday 26 Jan 2021.
    us = new_tracker(client, target_per_week=1, weekdays=[0], pause_on=["US"])
    kpi = tracker_in(calendar(client, "2021-05", today="2021-06-30"), us["id"])
    assert kpi["scheduled_days"] == [3, 10, 17, 24] and kpi["kpi"]["month_goal"] == 4
    assert kpi["kpi"]["per_week"][-1] == {"start_day": 31, "end_day": 31, "done": 0, "goal": 0}
    assert kpi["kpi"]["complete_weeks"] == 4, "a week whose goal is 0 is not counted"
    client.put(f"{API}/trackers/{us['id']}", json={"pause_on": []})
    assert tracker_in(calendar(client, "2021-05", today="2021-06-30"), us["id"])["kpi"]["month_goal"] == 5

    india = new_tracker(client, target_per_week=1, weekdays=[1], pause_on=["IN"])
    assert tracker_in(calendar(client, "2021-01", today="2021-02-01"), india["id"])["scheduled_days"] == [5, 12, 19]

    office = new_tracker(client, target_per_week=3, weekdays=[0, 1, 2, 3, 4], pause_on=["vacation"])
    v = client.post(f"{API}/vacations", json={"name": "ZZ Trip", "start_date": "2021-03-10", "end_date": "2021-03-12", "color": "#0f8a8a"}).json()
    k = tracker_in(calendar(client, "2021-03", today="2021-03-31"), office["id"])
    assert 10 not in k["scheduled_days"] and 9 in k["scheduled_days"]
    assert [w["goal"] for w in k["kpi"]["per_week"]] == [3, 1, 3, 3, 2], "week 2 keeps 2 of 5 days: 3 x 2/5 = 1.2 -> 1"
    client.delete(f"{API}/vacations/{v['id']}")
    assert [w["goal"] for w in tracker_in(calendar(client, "2021-03", today="2021-03-31"), office["id"])["kpi"]["per_week"]] == [3, 3, 3, 3, 2]


def test_cost_of_a_day(client):
    """Linked spending on ticked vs unticked scheduled days, up to today. Paused days and other spending are ignored."""
    c, _ = expense_cat(client, subs=())
    d, (x, y) = expense_cat(client, subs=("X", "Y"))
    noise, _ = expense_cat(client, subs=())
    office = new_tracker(client, target_per_week=3, weekdays=[0, 1, 2, 3, 4], pause_on=["vacation"],
                         cost_links=[{"category_id": c["id"]}, {"category_id": d["id"], "subcategory_id": x["id"]}])
    v = client.post(f"{API}/vacations", json={"name": "ZZ Leave", "start_date": "2021-03-10", "end_date": "2021-03-12", "color": "#0f8a8a"}).json()
    for day in (1, 2, 3, 8, 15, 16):
        tick(client, office["id"], f"2021-03-{day:02d}")
    for day, amount in ((1, 100), (2, 200), (3, 300), (4, 40)):
        spend(client, c["id"], f"2021-03-{day:02d}", amount)
    spend(client, d["id"], "2021-03-04", 60, sub=x["id"])
    spend(client, d["id"], "2021-03-01", 500, sub=y["id"])   # other sub-category: not linked
    spend(client, c["id"], "2021-03-11", 999)                 # a paused (vacation) day
    spend(client, noise["id"], "2021-03-05", 777)             # an unlinked category
    spend(client, c["id"], "2021-03-18", 5000)                # after today
    cost = tracker_in(calendar(client, "2021-03", today="2021-03-17"), office["id"])["kpi"]["cost"]
    # on: 1, 2, 3, 8, 15, 16 -> 600 / 6 = 100. off: 4, 5, 9, 17 -> (40 + 60) / 4 = 25.
    assert cost == {"avg_on": 100.0, "avg_off": 25.0, "n_on": 6, "n_off": 4, "diff": 75}
    assert tracker_in(calendar(client, "2021-03", today="2021-03-03"), office["id"])["kpi"]["cost"] is None, "no unticked day yet"

    client.delete(f"{API}/subcategories/{x['id']}")  # has expenses: refused, link stays
    assert len(next(t for t in client.get(f"{API}/trackers").json() if t["id"] == office["id"])["cost_links"]) == 2
    empty, (z,) = expense_cat(client, subs=("Z",))
    client.put(f"{API}/trackers/{office['id']}", json={"cost_links": [{"category_id": c["id"]}, {"category_id": empty["id"], "subcategory_id": z["id"]}]})
    assert client.delete(f"{API}/subcategories/{z['id']}").status_code == 200
    assert next(t for t in client.get(f"{API}/trackers").json() if t["id"] == office["id"])["cost_links"] == \
        [{"category_id": c["id"], "subcategory_id": None}], "deleting a sub-category drops links to it"
    assert client.delete(f"{API}/categories/{empty['id']}").status_code == 200
    client.delete(f"{API}/vacations/{v['id']}")


# ---------------------------------------------------------------- drag-to-move reminders

def test_move_this_month_only_and_every_month(client):
    cat = new_cat(client)
    r = new_rem(client, cat["id"], name="ZZ Move me", day=5)
    key = f"r{r['id']}"
    assert occ(calendar(client, "2021-04", today="2021-01-01"), key)["moved"] is False

    m = client.put(f"{API}/reminders/{r['id']}/move", json={"month": "2021-04", "day": 9, "scope": "month"})
    assert m.status_code == 200 and m.json()["day"] == 5, "a one-month move leaves the reminder's own day"
    april = occ(calendar(client, "2021-04", today="2021-01-01"), key)
    assert april["day"] == 9 and april["moved"] is True and april["state"] == "up"
    assert occ(calendar(client, "2021-05", today="2021-01-01"), key)["day"] == 5, "other months are untouched"
    assert occ(calendar(client, "2021-04", today="2021-04-07"), key)["state"] == "up", "state uses the moved date (9th)"

    client.put(f"{API}/reminders/{r['id']}/move", json={"month": "2021-04", "day": 12, "scope": "month"})
    assert occ(calendar(client, "2021-04", today="2021-01-01"), key)["day"] == 12, "moving again updates the override"
    client.put(f"{API}/reminders/{r['id']}/move", json={"month": "2021-04", "day": 5, "scope": "month"})
    back = occ(calendar(client, "2021-04", today="2021-01-01"), key)
    assert back["day"] == 5 and back["moved"] is False, "moving back to the normal day drops the override"

    client.put(f"{API}/reminders/{r['id']}/move", json={"month": "2021-04", "day": 20, "scope": "month"})
    a = client.put(f"{API}/reminders/{r['id']}/move", json={"month": "2021-04", "day": 15, "scope": "all"})
    assert a.json()["day"] == 15
    every = occ(calendar(client, "2021-04", today="2021-01-01"), key)
    assert (every["day"], every["moved"]) == (15, False), "'all' changes the day and drops that month's override"
    assert occ(calendar(client, "2021-07", today="2021-01-01"), key)["day"] == 15

    for bad in ({"month": "2021-04", "day": 31, "scope": "month"}, {"month": "2021-04", "day": 0, "scope": "all"},
                {"month": "2021-04", "day": 3, "scope": "sometimes"}, {"month": "April", "day": 3, "scope": "all"}):
        assert client.put(f"{API}/reminders/{r['id']}/move", json=bad).status_code == 400, bad
    yearly = new_rem(client, cat["id"], repeat="yearly", month=12, day=1)
    assert client.put(f"{API}/reminders/{yearly['id']}/move", json={"month": "2021-04", "day": 3, "scope": "month"}).status_code == 400, \
        "not in that month"
    assert client.put(f"{API}/reminders/999999/move", json={"month": "2021-04", "day": 3}).status_code == 404


def test_moved_instance_in_the_feed_and_cleanup(client):
    from test_reminders import events, feed, field
    cat = new_cat(client)
    r = new_rem(client, cat["id"], name="ZZ Feed move", day=5, amount=0)
    year = 2040  # after the series starts (it begins the month the reminder was created)
    client.put(f"{API}/reminders/{r['id']}/move", json={"month": f"{year}-03", "day": 9, "scope": "month"})
    client.put(f"{API}/reminders/{r['id']}/move", json={"month": f"{year}-04", "day": 30, "scope": "month"})
    evs = [e for e in events(feed(client, types=str(cat["id"]), today=f"{year}-01-01").text) if field(e, "UID") == f"reminder-{r['id']}@spendlens"]
    master = [e for e in evs if not any(ln.startswith("RECURRENCE-ID") for ln in e)]
    moved = [e for e in evs if any(ln.startswith("RECURRENCE-ID") for ln in e)]
    assert len(master) == 1 and field(master[0], "RRULE") == "FREQ=MONTHLY;BYMONTHDAY=5"
    pairs = sorted((field(e, "RECURRENCE-ID;VALUE=DATE"), field(e, "DTSTART;VALUE=DATE")) for e in moved)
    assert pairs == [(f"{year}0305", f"{year}0309"), (f"{year}0405", f"{year}0430")]
    assert all(field(e, "RRULE") is None and field(e, "SUMMARY") == "ZZ Feed move" for e in moved)

    client.delete(f"{API}/reminders/{r['id']}")
    from db.engine import SessionLocal
    from db.models import ReminderOverride
    s = SessionLocal()
    try:
        assert s.query(ReminderOverride).filter(ReminderOverride.reminder_id == r["id"]).count() == 0
    finally:
        s.close()


def test_every_occurrence_has_moved_flag(client):
    cat = new_cat(client)
    new_rem(client, cat["id"], day=3)
    cal = calendar(client, "2021-04", today="2021-01-01")
    assert cal["occurrences"] and all(o["moved"] in (True, False) for o in cal["occurrences"])
    assert isinstance(cal["trackers"], list)
