"""Role matrix: every API route is classified here, and every role is tried against every route.

Adding a route without adding it to EXPECTED fails `test_every_route_is_classified`, so nobody can ship an endpoint
whose permissions were never decided."""
import pytest
from fastapi.routing import APIRoute

from apihelpers import bearer

EXPECTED = {
    ("GET", "/api/setup/status"): "public",
    ("POST", "/api/setup"): "public",
    ("POST", "/api/auth/login"): "public",
    ("POST", "/api/auth/logout"): "viewer",
    ("GET", "/api/auth/me"): "viewer",
    ("POST", "/api/auth/ws-ticket"): "viewer",
    ("GET", "/api/users"): "admin",
    ("POST", "/api/users"): "admin",
    ("PATCH", "/api/users/{user_id}"): "admin",
    ("GET", "/api/switches"): "viewer",
    ("GET", "/api/switches/{dpid}"): "viewer",
    ("GET", "/api/rules"): "viewer",
    ("GET", "/api/rules/summary"): "viewer",
    ("GET", "/api/alerts"): "viewer",
    ("GET", "/api/alerts/{alert_id}"): "viewer",
    ("POST", "/api/alerts/{alert_id}/ack"): "analyst",
    ("GET", "/api/incidents"): "viewer",
    ("GET", "/api/incidents/{incident_id}"): "viewer",
    ("PATCH", "/api/incidents/{incident_id}"): "analyst",
    ("POST", "/api/incidents/{incident_id}/notes"): "analyst",
    ("GET", "/api/events"): "viewer",
    ("GET", "/api/probes"): "viewer",
    ("GET", "/api/ml/scores"): "viewer",
    ("GET", "/api/policies"): "viewer",
    ("PUT", "/api/policies"): "admin",
    ("GET", "/api/policies/history"): "analyst",
    ("GET", "/api/sessions"): "viewer",
    ("POST", "/api/sessions"): "admin",
    ("POST", "/api/sessions/{rec_id}/stop"): "admin",
    ("GET", "/api/sessions/{rec_id}/download"): "analyst",
    ("GET", "/api/reports/summary"): "viewer",
    ("GET", "/api/reports/alerts.csv"): "analyst",
    ("GET", "/api/audit"): "analyst",
    ("GET", "/api/audit/verify"): "admin",
    ("GET", "/api/engine/status"): "viewer",
    ("POST", "/api/engine/rotate-key"): "admin",
    ("GET", "/api/health"): "public",
    ("GET", "/api/health/detail"): "viewer",
}
RANK = {"viewer": 0, "analyst": 1, "admin": 2}
PARAMS = {"user_id": "999999", "dpid": "00000000000000ff", "alert_id": "nope", "incident_id": "999999", "rec_id": "nope"}
# routes whose side effect would break the rest of the matrix run (they are tested on their own)
SKIP_ALLOWED_CALL = {("POST", "/api/auth/logout")}


def api_routes(app):
    out = set()
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                out.add((m, r.path))
    return out


def concrete(path):
    for k, v in PARAMS.items():
        path = path.replace("{" + k + "}", v)
    return path


def test_every_route_is_classified(client):
    assert api_routes(client.app) == set(EXPECTED)


@pytest.mark.parametrize("route", sorted(k for k, v in EXPECTED.items() if v != "public"), ids=lambda r: f"{r[0]} {r[1]}")
def test_unauthenticated_requests_get_401(client, route):
    method, path = route
    assert client.request(method, concrete(path)).status_code == 401


def test_role_matrix(client, tokens):
    denied = 0
    for (method, path), need in sorted(EXPECTED.items()):
        if need == "public":
            continue
        for role, token in tokens.items():
            if RANK[role] >= RANK[need] and (method, path) in SKIP_ALLOWED_CALL:
                continue
            r = client.request(method, concrete(path), headers=bearer(token), json={})
            if RANK[role] >= RANK[need]:
                assert r.status_code not in (401, 403), (role, method, path, r.status_code, r.text)
            else:
                assert r.status_code == 403, (role, method, path, r.status_code, r.text)
                denied += 1
    assert denied > 0
    audit = client.get("/api/audit", params={"action": "permission_denied", "limit": 1000}, headers=bearer(tokens["admin"])).json()
    assert audit["total"] == denied, "every 403 must be in the audit log"
    assert {i["result"] for i in audit["items"]} == {"denied"}


def test_viewer_cannot_escalate_through_user_api(client, tokens):
    me = client.get("/api/auth/me", headers=bearer(tokens["viewer"])).json()
    r = client.patch(f"/api/users/{me['id']}", json={"role": "admin"}, headers=bearer(tokens["viewer"]))
    assert r.status_code == 403
    assert client.get("/api/auth/me", headers=bearer(tokens["viewer"])).json()["role"] == "viewer"
