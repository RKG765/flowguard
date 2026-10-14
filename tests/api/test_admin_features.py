"""Policies, reports (CSV safety), audit chain integrity, engine control, health, WebSocket stream, migrations."""
import csv
import io
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
    assert p["version"] == 1 and p["enforced"] is False and p["policy"]["dry_run"] is True
    r = client.put("/api/policies", json=GOOD_POLICY, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["updated_by"] == "admin"
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


def test_probes_and_ml_endpoints_say_they_are_not_built(client, tokens):
    h = bearer(tokens["viewer"])
    for path in ("/api/probes", "/api/ml/scores"):
        body = client.get(path, headers=h).json()
        assert body["available"] is False and body["items"] == [] and "Phase 5" in body["note"]


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
