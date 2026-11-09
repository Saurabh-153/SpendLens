"""The web hardening in security.py and auth_routes.py: sign-in throttling, sessions ending on a password change, the
cross-site request check, security headers and the CSV export's formula escaping."""
import csv
import io

import pytest

API = "/spendlens/api"


def test_failed_sign_ins_are_throttled_per_account(make_user, anon_client):
    _, u = make_user()
    _, other = make_user()
    wrong = {"email": u["email"], "password": "not-the-password"}
    for _ in range(5):
        assert anon_client.post(f"{API}/auth/login", json=wrong).status_code == 401
    r = anon_client.post(f"{API}/auth/login", json={"email": u["email"], "password": "user-test-pw"})
    assert r.status_code == 429 and "Too many failed attempts" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0
    # another account from the same address is not locked out by that
    assert anon_client.post(f"{API}/auth/login", json={"email": other["email"], "password": "user-test-pw"}).status_code == 200


def test_spraying_many_accounts_from_one_address_is_throttled(anon_client):
    for i in range(20):
        anon_client.post(f"{API}/auth/login", json={"email": f"spray-{i}@test.local", "password": "x"})
    assert anon_client.post(f"{API}/auth/login", json={"email": "spray-new@test.local", "password": "x"}).status_code == 429


def test_wrong_reset_codes_are_throttled(anon_client, monkeypatch):
    from routes import auth_routes
    monkeypatch.setattr(auth_routes, "is_local_request", lambda request: True)
    body = {"email": "admin@test.local", "new_password": "whatever-123", "code": "WRONGONE"}
    for _ in range(5):
        assert anon_client.post(f"{API}/auth/reset-local", json=body).status_code == 403
    assert anon_client.post(f"{API}/auth/reset-local", json=body).status_code == 429


def test_changing_the_password_ends_the_other_sign_ins_only(make_user, client):
    from fastapi.testclient import TestClient
    c, u = make_user(modules=["expense"])
    laptop = TestClient(client.app)
    assert laptop.post(f"{API}/auth/login", json={"email": u["email"], "password": "user-test-pw"}).status_code == 200
    assert c.post(f"{API}/auth/password", json={"current_password": "user-test-pw", "new_password": "newpassword1"}).status_code == 200
    assert c.get(f"{API}/auth/me").status_code == 200, "the session that changed it stays signed in"
    assert laptop.get(f"{API}/auth/me").status_code == 401, "every other session ends"


def test_session_cookie_secure_flag(make_user, client, monkeypatch):
    from fastapi.testclient import TestClient
    _, u = make_user()
    creds = {"email": u["email"], "password": "user-test-pw"}
    plain = TestClient(client.app).post(f"{API}/auth/login", json=creds)
    assert "secure" not in plain.headers["set-cookie"].lower(), "plain http: a Secure cookie would never come back"
    https = TestClient(client.app, base_url="https://testserver").post(f"{API}/auth/login", json=creds)
    assert "secure" in https.headers["set-cookie"].lower()
    monkeypatch.setenv("SPENDLENS_SECURE_COOKIE", "1")
    assert "secure" in TestClient(client.app).post(f"{API}/auth/login", json=creds).headers["set-cookie"].lower()


def test_is_local_request_accepts_the_dev_proxys_ipv4_mapped_loopback():
    from types import SimpleNamespace
    from routes.auth_routes import is_local_request
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"x-forwarded-for": "::ffff:127.0.0.1"})
    assert is_local_request(req)
    lan = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"x-forwarded-for": "::ffff:192.168.1.20"})
    assert not is_local_request(lan)


# ---------------------------------------------------------------- cross-site check and headers (security.install)

@pytest.fixture
def hardened(seeded_db, tmp_path):
    """The real router behind security.install, with a built index.html that has an inline script."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from fastapi.testclient import TestClient
    import security
    from routes.api import router

    index = tmp_path / "index.html"
    index.write_text("<html><head><script>document.title='x'</script></head>"
                     "<body><script type=\"module\" src=\"/assets/a.js\"></script></body></html>", encoding="utf-8")
    app = FastAPI()
    app.include_router(router)
    security.install(app, ["http://localhost:5173"], index)

    @app.get("/page")
    def page():
        return HTMLResponse(index.read_text(encoding="utf-8"))

    from conftest import ADMIN_EMAIL, ADMIN_PASSWORD
    c = TestClient(app)
    assert c.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200
    return c


def test_cross_site_writes_are_refused(hardened):
    body = {"module": "expense", "note": ""}
    r = hardened.post(f"{API}/access/requests", json=body, headers={"Origin": "http://localhost:6666"})
    assert r.status_code == 403 and r.json()["detail"] == "Cross-site request refused."
    assert hardened.post(f"{API}/access/requests", json=body, headers={"Origin": "null"}).status_code == 403
    # this server itself, a configured frontend, the dev proxy's original host, and no Origin at all are fine
    # (the admin has every module, so the request itself is refused with 409, past the check)
    for headers in ({"Origin": "http://testserver"}, {"Origin": "http://localhost:5173/"},
                    {"Origin": "http://localhost:3000", "X-Forwarded-Host": "localhost:3000"}, {}):
        assert hardened.post(f"{API}/access/requests", json=body, headers=headers).status_code == 409, headers
    # reads are not affected
    assert hardened.get(f"{API}/auth/me", headers={"Origin": "http://localhost:6666"}).status_code == 200


def test_security_headers(hardened):
    import security
    r = hardened.get(f"{API}/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["referrer-policy"] == "same-origin"
    assert "content-security-policy" not in r.headers, "JSON (and the Morningstar PDF) get no CSP"
    page = hardened.get("/page")
    csp = page.headers["content-security-policy"]
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert security.inline_script_hashes(None) == []
    import base64
    import hashlib
    want = base64.b64encode(hashlib.sha256(b"document.title='x'").digest()).decode()
    assert f"'sha256-{want}'" in csp and "frame-ancestors 'self'" in csp and "object-src 'none'" in csp


# ---------------------------------------------------------------- CSV export

def test_csv_cell_neutralises_formulas():
    from routes.investing_routes import csv_cell
    assert csv_cell('=HYPERLINK("http://x","y")') == '\'=HYPERLINK("http://x","y")'
    assert [csv_cell(v) for v in ("+1", "-x", "@SUM(A1)", "\tz")] == ["'+1", "'-x", "'@SUM(A1)", "'\tz"]
    assert csv_cell(-1234.5) == -1234.5 and csv_cell("Parag Parikh") == "Parag Parikh" and csv_cell(None) == ""


def test_portfolio_csv_parses_cleanly(client):
    r = client.get(f"{API}/export/portfolio")
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][0] == "Name" and len(rows[0]) == 12
    assert all(len(row) == 12 for row in rows), "a comma in a name no longer shifts the columns"
