"""Sign-in, per-user module access, and the request -> admin approval flow."""
import pytest

API = "/spendlens/api"

# One representative GET per module (all work with an empty database).
PROBE = {
    "expense": "/budget",
    "holdings": "/holdings",
    "ledger": "/equity/summary",
    "cards": "/cards",
}


def test_anonymous_gets_401_but_healthz_is_public(anon_client):
    assert anon_client.get(f"{API}/healthz").status_code == 200
    for path in PROBE.values():
        assert anon_client.get(f"{API}{path}").status_code == 401
    assert anon_client.get(f"{API}/auth/me").status_code == 401


def test_login_rejects_bad_credentials_the_same_way(anon_client, client):
    assert anon_client.post(f"{API}/auth/login", json={"email": "nobody@x.com", "password": "whatever1"}).status_code == 401
    r = anon_client.post(f"{API}/auth/login", json={"email": "admin@test.local", "password": "wrong"})
    assert r.status_code == 401 and r.json()["detail"] == "Wrong email or password."


def test_admin_has_every_module(client):
    me = client.get(f"{API}/auth/me").json()
    assert me["role"] == "admin" and set(me["modules"]) == set(PROBE)


@pytest.mark.parametrize("module", list(PROBE))
def test_each_module_is_gated_by_its_own_grant(make_user, module):
    without, _ = make_user(modules=[m for m in PROBE if m != module])
    with_it, _ = make_user(modules=[module])
    r = without.get(f"{API}{PROBE[module]}")
    assert r.status_code == 403 and r.headers["x-module"] == module
    assert with_it.get(f"{API}{PROBE[module]}").status_code == 200
    for other in PROBE:
        if other != module:
            assert with_it.get(f"{API}{PROBE[other]}").status_code == 403


def test_non_admin_cannot_reach_admin_or_database(make_user):
    c, _ = make_user(modules=list(PROBE))
    for path in ("/admin/users", "/admin/access/requests", "/database/overview"):
        assert c.get(f"{API}{path}").status_code == 403
    assert c.post(f"{API}/admin/users", json={"email": "a@b.co", "password": "longenough1"}).status_code == 403


def test_request_then_approve_unlocks(client, make_user):
    c, u = make_user(modules=["expense"])
    assert c.get(f"{API}{PROBE['ledger']}").status_code == 403
    r = c.post(f"{API}/access/requests", json={"module": "ledger", "note": "need it"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    # asking twice, or for what you already have, is refused
    assert c.post(f"{API}/access/requests", json={"module": "ledger"}).status_code == 409
    assert c.post(f"{API}/access/requests", json={"module": "expense"}).status_code == 409
    assert c.post(f"{API}/access/requests", json={"module": "nope"}).status_code == 400
    queue = [q for q in client.get(f"{API}/admin/access/requests?status=pending").json() if q["user_id"] == u["id"]]
    assert len(queue) == 1 and queue[0]["user_email"] == u["email"]
    assert client.post(f"{API}/admin/access/requests/{queue[0]['id']}/approve", json={"note": "ok"}).json()["status"] == "approved"
    assert c.get(f"{API}{PROBE['ledger']}").status_code == 200
    assert "ledger" in c.get(f"{API}/auth/me").json()["modules"]
    # a decided request cannot be decided again
    assert client.post(f"{API}/admin/access/requests/{queue[0]['id']}/reject").status_code == 409


def test_reject_does_not_unlock_and_user_can_ask_again(client, make_user):
    c, u = make_user()
    rid = c.post(f"{API}/access/requests", json={"module": "cards"}).json()["id"]
    assert client.post(f"{API}/admin/access/requests/{rid}/reject", json={"note": "not yet"}).json()["status"] == "rejected"
    assert c.get(f"{API}{PROBE['cards']}").status_code == 403
    assert c.post(f"{API}/access/requests", json={"module": "cards"}).status_code == 201
    mine = c.get(f"{API}/access/requests").json()
    assert [r["status"] for r in mine] == ["pending", "rejected"]
    assert mine[1]["decision_note"] == "not yet"


def test_admin_sets_and_revokes_modules(client, make_user):
    c, u = make_user(modules=["expense", "holdings"])
    assert c.get(f"{API}{PROBE['holdings']}").status_code == 200
    r = client.put(f"{API}/admin/users/{u['id']}/modules", json={"modules": ["expense", "ledger"]})
    assert r.status_code == 200 and r.json()["modules"] == ["expense", "ledger"]
    assert c.get(f"{API}{PROBE['holdings']}").status_code == 403
    assert c.get(f"{API}{PROBE['ledger']}").status_code == 200
    assert client.put(f"{API}/admin/users/{u['id']}/modules", json={"modules": ["bogus"]}).status_code == 400


def test_direct_grant_resolves_a_pending_request(client, make_user):
    c, u = make_user()
    c.post(f"{API}/access/requests", json={"module": "cards"})
    client.put(f"{API}/admin/users/{u['id']}/modules", json={"modules": ["cards"]})
    assert c.get(f"{API}/access/requests").json()[0]["status"] == "approved"


def test_deactivating_signs_the_user_out(client, make_user, anon_client):
    c, u = make_user(modules=["expense"])
    assert c.get(f"{API}{PROBE['expense']}").status_code == 200
    assert client.patch(f"{API}/admin/users/{u['id']}", json={"is_active": False}).status_code == 200
    assert c.get(f"{API}{PROBE['expense']}").status_code == 401
    assert anon_client.post(f"{API}/auth/login", json={"email": u["email"], "password": "user-test-pw"}).status_code == 401


def test_logout_and_password_change(make_user):
    c, u = make_user(modules=["expense"])
    assert c.post(f"{API}/auth/password", json={"current_password": "bad", "new_password": "newpassword1"}).status_code == 400
    assert c.post(f"{API}/auth/password", json={"current_password": "user-test-pw", "new_password": "newpassword1"}).status_code == 200
    c.post(f"{API}/auth/logout")
    assert c.get(f"{API}/auth/me").status_code == 401


def test_admin_cannot_demote_or_deactivate_self(client):
    me = client.get(f"{API}/auth/me").json()
    assert client.patch(f"{API}/admin/users/{me['id']}", json={"role": "user"}).status_code == 409
    assert client.patch(f"{API}/admin/users/{me['id']}", json={"is_active": False}).status_code == 409


def test_duplicate_email_and_short_password(client):
    body = {"email": "dup-zz@test.local", "password": "longenough1"}
    assert client.post(f"{API}/admin/users", json=body).status_code == 201
    assert client.post(f"{API}/admin/users", json={**body, "email": "DUP-ZZ@test.local"}).status_code == 409
    assert client.post(f"{API}/admin/users", json={"email": "x@y.co", "password": "short"}).status_code == 400



def test_password_reset_from_the_sign_in_page_is_local_only(anon_client, client, make_user, monkeypatch):
    import auth
    from routes import auth_routes
    c, u = make_user(modules=["expense"])
    code = auth.reset_code()
    body = {"email": u["email"], "new_password": "brand-new-pass1", "code": code}
    # the test client is not loopback, like a browser on another machine: refused even with the right code
    r = anon_client.post(f"{API}/auth/reset-local", json=body)
    assert r.status_code == 403 and "computer running SpendLens" in r.json()["detail"]
    monkeypatch.setattr(auth_routes, "is_local_request", lambda request: True)
    # loopback alone is not enough (a local proxy relaying another machine looks like loopback): the console's code is
    r = anon_client.post(f"{API}/auth/reset-local", json={**body, "code": ""})
    assert r.status_code == 403 and "reset code" in r.json()["detail"]
    assert anon_client.post(f"{API}/auth/reset-local", json={**body, "code": "WRONGONE"}).status_code == 403
    assert anon_client.post(f"{API}/auth/reset-local", json={**body, "new_password": "short"}).status_code == 400
    assert anon_client.post(f"{API}/auth/reset-local", json={**body, "email": "nobody@nowhere.test"}).status_code == 404
    lower = f"{code[:4]}-{code[4:]}".lower()   # typed as printed, in any case
    assert anon_client.post(f"{API}/auth/reset-local", json={**body, "code": lower}).status_code == 200
    assert auth.reset_code() != code, "a used code is replaced"
    assert anon_client.post(f"{API}/auth/reset-local", json=body).status_code == 403, "the old code no longer works"
    assert c.get(f"{API}/auth/me").status_code == 401, "the reset ended the user's existing sign-ins"
    assert anon_client.post(f"{API}/auth/login", json={"email": u["email"], "password": "brand-new-pass1"}).status_code == 200


def test_is_local_request_rejects_forwarded_requests():
    from types import SimpleNamespace
    from routes.auth_routes import is_local_request

    def req(host, **headers):
        return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)
    assert is_local_request(req("127.0.0.1")) and is_local_request(req("::1"))
    assert not is_local_request(req("192.168.1.20"))
    assert not is_local_request(req("127.0.0.1", **{"x-forwarded-for": "203.0.113.9"}))
    assert not is_local_request(req("127.0.0.1", forwarded="for=203.0.113.9"))
    assert is_local_request(req("127.0.0.1", **{"x-forwarded-for": "127.0.0.1"}))
