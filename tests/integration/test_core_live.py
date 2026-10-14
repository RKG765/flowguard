"""Phase 2 live tests: real OVS + Mininet + the real engine + the core service (in-process, receiver on).

Shows the whole path: ovs-ofctl attack -> engine detects/repairs -> ZeroMQ + spool -> core database -> REST and
WebSocket; plus the reliability claim that an alert raised while the core is DOWN arrives after it restarts."""
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import DPID, REPO, find_rule, ofctl

sys.path.insert(0, str(REPO))
from core.config import load_settings  # noqa: E402
from core.main import create_app  # noqa: E402

ADMIN = ("admin", "admin-pass-123")


@contextmanager
def core(lab):
    s = load_settings(data_dir=str(lab.data), start_receiver=True, spool_poll_seconds=0.3)
    with TestClient(create_app(s)) as c:
        if c.get("/api/setup/status").json()["needs_setup"]:
            assert c.post("/api/setup", json={"username": ADMIN[0], "password": ADMIN[1]}).status_code == 201
        tok = c.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}).json()["token"]
        c.cookies.clear()
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


def wait(pred, timeout=10.0, interval=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    return None


def alerts(c, kind=None):
    params = {"limit": 500}
    if kind:
        params["kind"] = kind
    return c.get("/api/alerts", params=params).json()["items"]


def test_switch_status_and_rule_integrity_reach_the_core(lab):
    with core(lab) as c:
        sw = wait(lambda: [s for s in c.get("/api/switches").json() if s["dpid"] == DPID and s["monitor_up"]], 15)
        assert sw, c.get("/api/switches").json()
        summary = wait(lambda: (lambda s: s if s["protected"] == 3 else None)(c.get("/api/rules/summary").json()), 15)
        assert summary and summary["verified"] == 3 and summary["verified_percent"] == 100.0
        eng = c.get("/api/engine/status").json()
        assert eng["known"] and eng["status"]["epoch"] == 1


def test_attack_appears_live_on_websocket_and_rest_and_is_acknowledged(lab):
    with core(lab) as c:
        ticket = c.post("/api/auth/ws-ticket").json()["ticket"]
        with c.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
            assert ws.receive_json()["type"] == "hello"
            t0 = time.time()
            ofctl("add-flow", "s1", "table=0,priority=300,arp,actions=drop")
            got = None
            while time.time() - t0 < 10:
                m = ws.receive_json()
                if m["type"] == "alert" and m["data"]["kind"] == "forged":
                    got = m["data"]
                    break
            assert got, "the alert must arrive on the WebSocket"
            assert time.time() - t0 < 5
        a = wait(lambda: [x for x in alerts(c, "forged") if x["id"] == got["id"]])
        assert a and a[0]["action"] == "removed" and a[0]["incident_id"]
        restored = wait(lambda: c.get(f"/api/alerts/{got['id']}").json()["time_to_restore_ms"] is not None)
        assert restored, "the engine's restore confirmation (alert_update) must reach the core"
        ack_path = lab.spool.parent / (lab.spool.name + ".ack")
        assert wait(lambda: ack_path.exists() and int(ack_path.read_text()) >= got["seq"]), "core must acknowledge the spool"
        assert find_rule(0, 300) is None


def test_alert_raised_while_core_is_down_arrives_after_restart(lab):
    """While the core is down the alert sits in BOTH the engine's in-memory channel queue and its durable spool, so
    this live test proves delivery after a restart but not which path delivered it. The spool-only path (needed when
    the engine's memory queue is lost too) is proven by tests/api/test_ingest.py::test_spool_tail_*."""
    with core(lab) as c:
        before = {a["id"] for a in alerts(c)}
    # the core is stopped now: only the engine's durable spool sees this attack
    ofctl("--strict", "del-flows", "s1", "table=0,priority=100,tcp,tp_dst=23")
    assert lab.wait(lambda: lab.alerts(kind="missing"), 6), "engine must still detect while the core is down"
    assert lab.wait(lambda: find_rule(0, 100, "tcp,tp_dst=23"), 6)
    with core(lab) as c:
        new = wait(lambda: [a for a in alerts(c, "missing") if a["id"] not in before], 10)
        assert new, "the missed alert must be picked up from the spool after the core restarts"
        spool_ids = {a["id"] for a in lab.alerts()}
        stored = {a["id"] for a in alerts(c)}
        assert spool_ids <= stored, f"every engine alert must be in the core: missing {spool_ids - stored}"


def test_policy_churn_creates_no_alerts_in_the_core(lab):
    with core(lab) as c:
        time.sleep(2.0)
        n0 = len(alerts(c))
        text = lab.policy.read_text()
        lab.policy.write_text(text + "  - {table: 0, priority: 95, match: {eth_type: 0x0800, ip_proto: 17, udp_dst: 5353}, instructions: []}\n")
        assert lab.wait(lambda: find_rule(0, 95, "udp"), 6)
        time.sleep(4.0)
        assert len(alerts(c)) == n0, [a["kind"] for a in alerts(c)[: len(alerts(c)) - n0]]
        summary = wait(lambda: (lambda s: s if s["protected"] == 4 and s["verified"] == 4 else None)(c.get("/api/rules/summary").json()), 12)
        assert summary, c.get("/api/rules/summary").json()


def test_key_rotation_requested_through_the_api(lab):
    with core(lab) as c:
        assert c.post("/api/engine/rotate-key").status_code == 202
        ev = wait(lambda: [e for e in c.get("/api/events", params={"kind": "key_rotated"}).json()], 10)
        assert ev and ev[0]["data"]["epoch"] == 2
        assert wait(lambda: c.get("/api/engine/status").json()["status"]["epoch"] == 2, 12)
        audit = c.get("/api/audit", params={"action": "key_rotation_requested"}).json()
        assert audit["total"] == 1
