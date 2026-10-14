"""First-run setup, login, sessions, CSRF, lockout, user management."""
import time

import pytest
from fastapi.testclient import TestClient

from apihelpers import PASSWORDS, bearer, login
from core.config import load_settings
from core.main import create_app


def test_first_run_setup_only_once(client):
    assert client.get("/api/setup/status").json() == {"needs_setup": True}
    assert client.post("/api/setup", json={"username": "admin", "password": "short"}).status_code == 422
    assert client.post("/api/setup", json={"username": "admin", "password": "admin"}).status_code == 422
    r = client.post("/api/setup", json={"username": "admin", "password": PASSWORDS["admin"]})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert client.get("/api/setup/status").json() == {"needs_setup": False}
    assert client.post("/api/setup", json={"username": "evil", "password": "evil-pass-123"}).status_code == 409


def test_login_returns_token_cookie_and_csrf(client, tokens):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORDS["admin"]})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin" and body["token"] and body["csrf_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "fg_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "password_hash" not in r.text


def test_wrong_password_and_unknown_user_look_the_same(client, tokens):
    a = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass-123"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong-pass-123"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_lockout_after_repeated_failures(client, tokens):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "viewer", "password": "nope-nope-1"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "viewer", "password": PASSWORDS["viewer"]})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1  # even the right password is refused for now
    # other users are not affected
    assert client.post("/api/auth/login", json={"username": "analyst", "password": PASSWORDS["analyst"]}).status_code == 200
    audit = client.get("/api/audit", params={"action": "login_failed"}, headers=bearer(tokens["admin"])).json()
    assert audit["total"] == 5


def test_logout_revokes_the_session(client, tokens):
    t = login(client, "viewer")
    assert client.get("/api/auth/me", headers=bearer(t)).status_code == 200
    assert client.post("/api/auth/logout", headers=bearer(t)).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(t)).status_code == 401


def test_cookie_sessions_need_csrf_for_changes_bearer_does_not(client, tokens):
    r = client.post("/api/auth/login", json={"username": "analyst", "password": PASSWORDS["analyst"]})
    csrf = r.json()["csrf_token"]  # the TestClient now holds the session cookie
    assert client.get("/api/auth/me").status_code == 200                      # reads need no CSRF token
    assert client.post("/api/alerts/x/ack").status_code == 403                # change without token: refused
    assert client.post("/api/alerts/x/ack", headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/alerts/x/ack", headers={"X-CSRF-Token": csrf}).status_code == 404  # passes CSRF; no such alert
    client.cookies.clear()
    assert client.post("/api/alerts/x/ack", headers=bearer(tokens["analyst"])).status_code == 404
    audit = client.get("/api/audit", params={"action": "csrf_rejected"}, headers=bearer(tokens["admin"])).json()
    assert audit["total"] == 2


def test_session_expiry(tmp_path):
    s = load_settings(data_dir=str(tmp_path / "d"), start_receiver=False, session_ttl_hours=0.5 / 3600)
    with TestClient(create_app(s)) as c:
        c.post("/api/setup", json={"username": "admin", "password": PASSWORDS["admin"]})
        t = login(c, "admin")
        assert c.get("/api/auth/me", headers=bearer(t)).status_code == 200
        time.sleep(0.8)
        assert c.get("/api/auth/me", headers=bearer(t)).status_code == 401


def test_disabling_a_user_kills_their_sessions(client, tokens):
    users = client.get("/api/users", headers=bearer(tokens["admin"])).json()
    vid = next(u["id"] for u in users if u["username"] == "viewer")
    assert client.patch(f"/api/users/{vid}", json={"disabled": True}, headers=bearer(tokens["admin"])).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(tokens["viewer"])).status_code == 401
    assert client.post("/api/auth/login", json={"username": "viewer", "password": PASSWORDS["viewer"]}).status_code == 401


def test_last_admin_cannot_be_demoted_or_disabled(client, tokens):
    aid = client.get("/api/auth/me", headers=bearer(tokens["admin"])).json()["id"]
    assert client.patch(f"/api/users/{aid}", json={"role": "viewer"}, headers=bearer(tokens["admin"])).status_code == 409
    assert client.patch(f"/api/users/{aid}", json={"disabled": True}, headers=bearer(tokens["admin"])).status_code == 409


def test_user_creation_rules(client, tokens):
    h = bearer(tokens["admin"])
    assert client.post("/api/users", json={"username": "viewer", "password": "whatever-123", "role": "viewer"}, headers=h).status_code == 409
    assert client.post("/api/users", json={"username": "bad name!", "password": "whatever-123", "role": "viewer"}, headers=h).status_code == 422
    assert client.post("/api/users", json={"username": "x1x", "password": "whatever-123", "role": "root"}, headers=h).status_code == 422
    r = client.get("/api/users", headers=h)
    assert all("password_hash" not in u for u in r.json())


def test_password_change_revokes_sessions_and_new_password_works(client, tokens):
    h = bearer(tokens["admin"])
    aid = next(u["id"] for u in client.get("/api/users", headers=h).json() if u["username"] == "analyst")
    assert client.patch(f"/api/users/{aid}", json={"password": "new-analyst-456"}, headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(tokens["analyst"])).status_code == 401
    assert login(client, "analyst", "new-analyst-456")
