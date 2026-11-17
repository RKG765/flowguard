"""Policies, reports (CSV safety), audit chain integrity, engine control, health, WebSocket stream, migrations."""
import csv
import io
import json
import os
import time

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from starlette.websockets import WebSocketDisconnect

from apihelpers import alert_rec, bearer
from core import db as dbmod
from core.models import Base

GOOD_POLICY = {"dry_run": False, "response_mode": "restore", "critical_tables": [0, 2],
               "weights": {"l1": 1.0, "l2": 0.7, "l3": 0.3}, "thresholds": {"alert": 0.2, "restore": 0.5, "quarantine": 0.9},
               "actions": {"critical": "quarantine_port", "high": "restore_and_alert", "medium": "alert_only", "low": "none"}}


# ---- policies ------------------------------------------------------------------------------------------------
def test_policy_default_versioning_and_history(client, tokens):
    h = bearer(tokens["admin"])
    p = client.get("/api/policies", headers=bearer(tokens["viewer"])).json()
    assert p["version"] == 1 and p["enforced"] is True and p["policy"]["dry_run"] is True
    assert p["enforced_fields"] == ["dry_run", "weights", "thresholds", "actions"]  # response_mode/critical_tables stay in the engine config
    r = client.put("/api/policies", json=GOOD_POLICY, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["updated_by"] == "admin"
    # the enforced part is handed to the engine as control/risk-policy.json
    handed = json.load(open(os.path.join(client.app.state.settings.control_dir, "risk-policy.json")))
    assert handed == {k: GOOD_POLICY[k] for k in ("dry_run", "weights", "thresholds", "actions")}
    hist = client.get("/api/policies/history", headers=bearer(tokens["analyst"])).json()
    assert [x["version"] for x in hist] == [2, 1]
    audit = client.get("/api/audit", params={"action": "policy_updated"}, headers=h).json()
    assert audit["total"] == 1 and "critical_tables" in audit["items"][0]["details"]["changed"]


@pytest.mark.parametrize("change", [
    {"weights": {"l1": 1.5, "l2": 0.7, "l3": 0.3}},
    {"thresholds": {"alert": 0.9, "restore": 0.5, "quarantine": 0.4}},
    {"critical_tables": [255]}, {"critical_tables": [0, 0]}, {"critical_tables": []},
    {"response_mode": "delete_everything"}, {"actions": {"high": "rm -rf /"}},
])
def test_invalid_policies_are_rejected(client, tokens, change):
    r = client.put("/api/policies", json=dict(GOOD_POLICY, **change), headers=bearer(tokens["admin"]))
    assert r.status_code == 422
    assert client.get("/api/policies", headers=bearer(tokens["admin"])).json()["version"] == 1


# ---- reports -----------------------------------------------------------------------------------------------------
def test_summary_is_computed_from_stored_alerts_only(client, tokens):
    empty = client.get("/api/reports/summary", headers=bearer(tokens["viewer"])).json()
    assert empty["alerts_total"] == 0 and empty["detect_latency_ms"] is None  # nothing invented
    ing = client.app.state.ingestor
    for i, lat in enumerate((10.0, 20.0, 30.0)):
        ing.ingest(alert_rec(f"{i:032d}", seq=i + 1, timing={"detect_latency_ms": lat}), "test")
    s = client.get("/api/reports/summary", headers=bearer(tokens["viewer"])).json()
    assert s["alerts_total"] == 3 and s["detect_latency_ms"] == {"n": 3, "mean": 20.0, "median": 20.0, "p95": 30.0}


def test_csv_export_neutralises_formula_injection(client, tokens):
    client.app.state.ingestor.ingest(alert_rec(summary='=HYPERLINK("http://evil","x")'), "test")
    r = client.get("/api/reports/alerts.csv", headers=bearer(tokens["analyst"]))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert rows[0]["summary"].startswith("'=")


# ---- audit log -----------------------------------------------------------------------------------------------------
def test_audit_chain_verifies_and_detects_tampering(client, tokens, settings):
    h = bearer(tokens["admin"])
    client.put("/api/policies", json=GOOD_POLICY, headers=h)
    v = client.get("/api/audit/verify", headers=h).json()
    assert v["ok"] is True and v["rows_checked"] >= 5
    eng = create_engine(settings.db_url)
    with eng.begin() as conn:  # an attacker with database access edits one row in the middle
        conn.execute(text("UPDATE audit_events SET username='someone-else' WHERE id = 2"))
    v = client.get("/api/audit/verify", headers=h).json()
    assert v["ok"] is False and v["first_bad_id"] == 2


def test_audit_rows_carry_who_what_where_and_no_secrets(client, tokens):
    items = client.get("/api/audit", headers=bearer(tokens["admin"])).json()["items"]
    created = next(i for i in items if i["action"] == "user_created")
    assert created["username"] == "admin" and created["role"] == "admin" and created["ip"] and created["target"] in ("analyst", "viewer")
    blob = str(items)
    assert "admin-pass-123" not in blob and "argon2" not in blob


def test_audit_strips_control_characters(client, tokens):
    client.post("/api/auth/login", json={"username": "admin", "password": "wrong-one-1"},
                headers={"User-Agent": "evil\r\nFAKE AUDIT LINE"})
    item = client.get("/api/audit", params={"action": "login_failed"}, headers=bearer(tokens["admin"])).json()["items"][0]
    assert "\n" not in item["user_agent"] and "\r" not in item["user_agent"]


# ---- engine control and health -----------------------------------------------------------------------------------
def test_rotate_key_writes_the_engine_control_file(client, tokens, settings):
    r = client.post("/api/engine/rotate-key", headers=bearer(tokens["admin"]))
    assert r.status_code == 202
    assert os.path.exists(os.path.join(settings.control_dir, "rotate"))
    acts = [i["action"] for i in client.get("/api/audit", headers=bearer(tokens["admin"])).json()["items"]]
    assert "key_rotation_requested" in acts


def test_health_public_is_minimal_detail_needs_login(client, tokens):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    d = client.get("/api/health/detail", headers=bearer(tokens["viewer"])).json()
    assert d["database"] == "ok" and d["engine"] == {"known": False}


def test_probes_and_ml_endpoints_are_empty_and_honest_before_the_engine_reports(client, tokens):
    h = bearer(tokens["viewer"])
    for path in ("/api/probes", "/api/ml/scores"):
        body = client.get(path, headers=h).json()
        assert body["available"] is False and body["items"] == [] and body["note"].startswith("no ")


def test_openapi_lists_the_api(client):
    spec = client.get("/openapi.json").json()
    assert "/api/alerts" in spec["paths"] and "/api/auth/login" in spec["paths"]


# ---- WebSocket ---------------------------------------------------------------------------------------------------
def test_websocket_requires_a_one_time_ticket_and_streams_alerts(client, tokens):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws?ticket=forged") as ws:
            ws.receive_json()
    ticket = client.post("/api/auth/ws-ticket", headers=bearer(tokens["viewer"])).json()["ticket"]
    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["data"]["role"] == "viewer"
        client.app.state.ingestor.ingest(alert_rec(), "test")
        msg = ws.receive_json()
        assert msg["type"] == "alert" and msg["data"]["kind"] == "forged"
    with pytest.raises(WebSocketDisconnect):  # the ticket was single use
        with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
            ws.receive_json()


# ---- migrations ----------------------------------------------------------------------------------------------------
def test_migrations_match_the_models(tmp_path):
    url = f"sqlite:///{tmp_path}/m.db"
    dbmod.upgrade(url)
    dbmod.upgrade(url)  # idempotent
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models changed without a migration: {diff}"


# ---- built dashboard served by the core (single port for demos and Phase 7) --------------------------------
def test_core_serves_the_built_dashboard_with_spa_fallback(tmp_path):
    from fastapi.testclient import TestClient
    from core.config import load_settings
    from core.main import create_app
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>FlowGuard shell</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside dist")
    s = load_settings(data_dir=str(tmp_path / "d"), start_receiver=False, web_dist=str(dist))
    with TestClient(create_app(s)) as c:
        assert "FlowGuard shell" in c.get("/").text
        assert "FlowGuard shell" in c.get("/rules").text           # client-side route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/assets/missing.js").status_code == 404
        assert c.get("/..%2Fsecret.txt").status_code == 404        # never outside dist
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json() == {"status": "ok"}       # the API still wins


# ---- Phase 5: L2 probe results and L3 scores flow engine -> core -> API ----------------------------------------------------
def test_probe_results_and_ml_scores_are_stored_and_served(client, tokens):
    h = bearer(tokens["viewer"])
    assert client.get("/api/probes", headers=h).json()["available"] is False  # nothing invented before the engine reports
    ing = client.app.state.ingestor
    ing.ingest({"type": "probe_result", "t": time.time(), "dpid": "0000000000000001", "table_id": 0, "priority": 100,
                "status": "fail", "reason": "forwarding differs"}, "test")
    ing.ingest({"type": "ml_score", "t": time.time(), "dpid": "0000000000000001", "score": 0.81, "reasons": ["rare drop"]}, "test")
    p = client.get("/api/probes", headers=h).json()
    m = client.get("/api/ml/scores", headers=h).json()
    assert p["available"] is True and p["items"][0]["data"]["status"] == "fail"
    assert m["available"] is True and m["items"][0]["score"] == 0.81


# ---- port quarantine API: role gating and input validation ---------------------------------------------------------------------
def test_quarantine_endpoints_are_role_gated_and_validated(client, tokens):
    assert client.get("/api/quarantine").status_code == 401
    assert client.get("/api/quarantine", headers=bearer(tokens["viewer"])).json() == {"items": []}
    body = {"dpid": "0000000000000001", "port": 2}
    for role in ("viewer", "analyst"):
        assert client.post("/api/quarantine/release", json=body, headers=bearer(tokens[role])).status_code == 403
    admin = bearer(tokens["admin"])
    assert client.post("/api/quarantine/release", json={"dpid": "not-hex", "port": 2}, headers=admin).status_code == 422
    assert client.post("/api/quarantine/release", json={"dpid": "1", "port": 0}, headers=admin).status_code == 422
    assert client.post("/api/quarantine/release", json={"dpid": "1", "port": 4294967295}, headers=admin).status_code == 422
    assert client.post("/api/quarantine/release", json=body, headers=admin).status_code == 202
    assert any(f.startswith("release-") for f in os.listdir(client.app.state.settings.control_dir))
    assert client.get("/api/audit", params={"action": "quarantine_release_requested"}, headers=admin).json()["total"] == 1


@pytest.mark.parametrize("change", [{"weights": {"l1": 0, "l2": 0, "l3": 0}}, {"actions": {"critical": "alert_only"}}])
def test_policies_the_engine_would_reject_are_rejected_by_the_api_too(client, tokens, change):
    r = client.put("/api/policies", json=dict(GOOD_POLICY, **change), headers=bearer(tokens["admin"]))
    assert r.status_code == 422
