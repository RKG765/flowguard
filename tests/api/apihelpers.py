"""Helpers shared by the core API tests (a uniquely named module: several conftest.py files exist in tests/)."""
import time

PASSWORDS = {"admin": "admin-pass-123", "analyst": "analyst-pass-123", "viewer": "viewer-pass-123"}
DPID = "0000000000000001"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, username, password=None):
    r = client.post("/api/auth/login", json={"username": username, "password": password or PASSWORDS[username]})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # tests use Bearer tokens unless they test cookies on purpose
    return r.json()["token"]


def alert_rec(aid="a" * 32, seq=1, kind="forged", priority=300, match=None, t=None, **extra):
    rec = {"type": "alert", "id": aid, "seq": seq, "t": t or time.time(), "kind": kind, "severity": "high", "layer": "L1",
           "dpid": DPID, "table_id": 0, "priority": priority, "match": match if match is not None else {"eth_type": 2054},
           "action": "removed", "detected_by": "monitor_event",
           "summary": "An unknown rule that the controller did not install appeared on the switch.",
           "timing": {"detect_latency_ms": 18.0}}
    rec.update(extra)
    return rec


def snapshot_rec(t=None):
    return {"type": "snapshot", "dpid": DPID, "table_id": 0, "t": t or time.time(), "epoch": 1, "rules": [
        {"table_id": 0, "priority": 100, "match": {"tcp_dst": 23}, "instructions": [], "cookie": "00000000000a0001",
         "status": "ok", "golden": True, "golden_cookie": "00000000000a0001", "present": True},
        {"table_id": 0, "priority": 90, "match": {"tcp_dst": 22}, "instructions": [], "cookie": None,
         "status": "missing", "golden": True, "golden_cookie": "00000000000b0001", "present": False},
        {"table_id": 0, "priority": 300, "match": {"eth_type": 2054}, "instructions": [], "cookie": "0000000000000000",
         "status": "forged", "golden": False, "golden_cookie": None, "present": True}]}
