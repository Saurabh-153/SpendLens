"""A card's benefits, written down: seeded once from its scheme, then yours to edit."""
import pytest

import card_perks as P
from test_cards_accounts import icici_clean  # noqa: F401  (fixture)

API = "/spendlens/api"


def new_card(client, name, profile="generic", last4=""):
    r = client.post(f"{API}/cards", json={"name": name, "profile": profile, "last4": last4, "issuer": "Test Bank"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_every_scheme_with_terms_has_seeds_and_each_is_valid():
    assert set(P.SEEDS) == set(P.C.PROFILES) - {"generic"}
    for profile, seeds in P.SEEDS.items():
        assert seeds, profile
        for s in seeds:
            assert s["kind"] in P.KIND_IDS and s["title"] and s["value_yr"] >= 0


def test_a_scheme_card_starts_with_its_published_terms_all_marked_to_check(client, seeded_db):
    cid = new_card(client, "ZZ Perk Amex", "amex_smartearn", "88001")
    d = client.get(f"{API}/cards/{cid}/perks").json()
    assert len(d["perks"]) == len(P.SEEDS["amex_smartearn"])
    assert d["to_check"] == len(d["perks"]) and not any(p["checked"] for p in d["perks"])
    assert d["value_yr"] == 1500, "the estimated yearly value of the entries that carry one"


def test_a_placeholder_scheme_has_no_entries_and_you_can_add_your_own(client, seeded_db):
    cid = new_card(client, "ZZ Perk Blank")
    assert client.get(f"{API}/cards/{cid}/perks").json()["perks"] == []
    d = client.post(f"{API}/cards/{cid}/perks", json={"kind": "lounge", "title": "Priority Pass", "detail": "6 visits", "value_yr": 3000}).json()
    assert [(p["title"], p["kind"], p["checked"], p["source"]) for p in d["perks"]] == [("Priority Pass", "lounge", True, "Added by you")]
    assert d["value_yr"] == 3000 and d["to_check"] == 0


def test_seeding_happens_once_so_a_deleted_entry_stays_deleted(client, seeded_db):
    cid = new_card(client, "ZZ Perk Once", "bob_eterna", "88002")
    first = client.get(f"{API}/cards/{cid}/perks").json()["perks"]
    client.delete(f"{API}/cards/perks/{first[0]['id']}")
    again = client.get(f"{API}/cards/{cid}/perks").json()["perks"]
    assert len(again) == len(first) - 1 and first[0]["id"] not in [p["id"] for p in again]


def test_ticking_an_entry_checks_it_and_rewording_it_counts_as_checked(client, seeded_db):
    cid = new_card(client, "ZZ Perk Edit", "hdfc_neu", "88003")
    ps = client.get(f"{API}/cards/{cid}/perks").json()["perks"]
    d = client.patch(f"{API}/cards/perks/{ps[0]['id']}", json={"checked": True}).json()
    assert next(p for p in d["perks"] if p["id"] == ps[0]["id"])["checked"] and d["to_check"] == len(ps) - 1
    d = client.patch(f"{API}/cards/perks/{ps[1]['id']}", json={"title": "1.5% on all spend", "value_yr": 500}).json()
    p = next(p for p in d["perks"] if p["id"] == ps[1]["id"])
    assert (p["title"], p["value_yr"], p["checked"]) == ("1.5% on all spend", 500, True)


@pytest.mark.parametrize("body", [{"title": ""}, {"title": "x", "kind": "nope"}, {"title": "x", "value_yr": -5}])
def test_a_bad_entry_is_refused(client, seeded_db, body):
    cid = new_card(client, "ZZ Perk Bad" + str(abs(hash(str(body))) % 999), "generic")
    assert client.post(f"{API}/cards/{cid}/perks", json=body).status_code == 400


def test_unknown_ids_are_404(client, seeded_db):
    assert client.patch(f"{API}/cards/perks/999999", json={"checked": True}).status_code == 404
    assert client.delete(f"{API}/cards/perks/999999").status_code == 404
    assert client.post(f"{API}/cards/999999/perks", json={"title": "x"}).status_code == 404


def test_one_physical_card_shares_one_list_across_its_numbers(client, icici_clean, monkeypatch):  # noqa: F811
    from test_cards_admin import two_cards
    a, _ = two_cards(client, monkeypatch)
    client.patch(f"{API}/cards/{a['id']}", json={"profile": "icici_rubyx"})
    d = client.post(f"{API}/cards/{a['id']}/perks", json={"title": "Mine"}).json()
    assert any(p["title"] == "Mine" for p in d["perks"])
    assert client.get(f"{API}/cards/{a['members'][0]}/perks").json()["perks"] == d["perks"], "every number reads the same list"
