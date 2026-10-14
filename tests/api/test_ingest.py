"""Engine -> core ingest: idempotency, incident grouping, rule snapshots, the ordered spool reader with acknowledgement,
the real ZeroMQ receiver, recordings."""
import json
import os
import time

import pytest
import zmq
from fastapi.testclient import TestClient

from apihelpers import DPID, PASSWORDS, alert_rec, bearer, login, snapshot_rec
from core.config import load_settings
from core.ingest import DUPLICATE, ERROR, IGNORED, OK, SpoolTail, write_ack
from core.main import create_app
from engine.spool import AlertSpool


def ingest(client, rec):
    return client.app.state.ingestor.ingest(rec, "test")


def test_alert_is_stored_once_and_visible(client, tokens):
    rec = alert_rec()
    assert ingest(client, rec) == OK
    assert ingest(client, rec) == DUPLICATE
    r = client.get("/api/alerts", headers=bearer(tokens["viewer"])).json()
    assert r["total"] == 1 and r["items"][0]["kind"] == "forged" and r["items"][0]["detect_latency_ms"] == 18.0
    full = client.get(f"/api/alerts/{rec['id']}", headers=bearer(tokens["viewer"])).json()
    assert full["details"]["match"] == {"eth_type": 2054}


def test_alert_update_sets_restore_time_once(client, tokens):
    rec = alert_rec()
    ingest(client, rec)
    upd = {"type": "alert_update", "alert_id": rec["id"], "kind": "restored", "t": time.time(), "seq": 2,
           "timing": {"time_to_restore_ms": 7.5}}
    assert ingest(client, upd) == OK
    assert ingest(client, upd) == DUPLICATE
    a = client.get(f"/api/alerts/{rec['id']}", headers=bearer(tokens["viewer"])).json()
    assert a["time_to_restore_ms"] == 7.5 and a["restored_at"]


def test_alerts_on_the_same_rule_slot_group_into_one_incident(client, tokens):
    ingest(client, alert_rec("1" * 32, 1))
    ingest(client, alert_rec("2" * 32, 2))
    ingest(client, alert_rec("3" * 32, 3, priority=200, match={"tcp_dst": 23}, kind="shadow"))
    inc = client.get("/api/incidents", headers=bearer(tokens["viewer"])).json()
    assert inc["total"] == 2
    counts = sorted(i["alert_count"] for i in inc["items"])
    assert counts == [1, 2]
    big = next(i for i in inc["items"] if i["alert_count"] == 2)
    detail = client.get(f"/api/incidents/{big['id']}", headers=bearer(tokens["viewer"])).json()
    assert [a["id"] for a in detail["alerts"]] == ["1" * 32, "2" * 32]


def test_closed_incident_is_not_reused_and_analyst_workflow_is_audited(client, tokens):
    ingest(client, alert_rec("1" * 32, 1))
    iid = client.get("/api/incidents", headers=bearer(tokens["viewer"])).json()["items"][0]["id"]
    h = bearer(tokens["analyst"])
    assert client.patch(f"/api/incidents/{iid}", json={"assignee": "analyst"}, headers=h).json()["assignee"] == "analyst"
    assert client.post(f"/api/incidents/{iid}/notes", json={"text": "looked at it"}, headers=h).status_code == 201
    assert client.patch(f"/api/incidents/{iid}", json={"status": "closed"}, headers=h).json()["closed_at"]
    ingest(client, alert_rec("2" * 32, 2))
    assert client.get("/api/incidents", headers=bearer(tokens["viewer"])).json()["total"] == 2
    acts = [e["action"] for e in client.get("/api/audit", headers=bearer(tokens["admin"])).json()["items"]]
    assert acts.count("incident_updated") == 2 and "incident_note_added" in acts


def test_ack_alert(client, tokens):
    rec = alert_rec()
    ingest(client, rec)
    a = client.post(f"/api/alerts/{rec['id']}/ack", headers=bearer(tokens["analyst"])).json()
    assert a["status"] == "acknowledged" and a["acknowledged_by"] == "analyst"


def test_rule_snapshot_gives_integrity_status_and_summary(client, tokens):
    assert ingest(client, snapshot_rec()) == OK
    h = bearer(tokens["viewer"])
    rules = client.get("/api/rules", headers=h).json()
    assert {r["priority"]: r["status"] for r in rules} == {100: "ok", 90: "missing", 300: "forged"}
    assert [r["priority"] for r in client.get("/api/rules", params={"status": "forged"}, headers=h).json()] == [300]
    s = client.get("/api/rules/summary", headers=h).json()
    assert s["protected"] == 2 and s["verified"] == 1 and s["verified_percent"] == 50.0
    old = snapshot_rec(t=time.time() - 100)
    assert ingest(client, old) == DUPLICATE, "an older snapshot never overwrites a newer one"
    sw = client.get("/api/switches", headers=h).json()
    assert sw[0]["dpid"] == DPID and sw[0]["connected"] is True


def test_engine_status_and_events_update_switches(client, tokens):
    t = time.time()
    ingest(client, {"type": "engine_status", "t": t, "switches": [DPID], "monitors_up": {DPID: True}, "spool": {"acked": 0}})
    ingest(client, {"type": "event", "kind": "switch_connected", "dpid": "0000000000000002", "t": t})
    h = bearer(tokens["viewer"])
    sw = {s["dpid"]: s for s in client.get("/api/switches", headers=h).json()}
    assert sw[DPID]["monitor_up"] is True and sw["0000000000000002"]["connected"] is True
    st = client.get("/api/engine/status", headers=h).json()
    assert st["known"] and st["stale"] is False
    assert client.get("/api/events", headers=h).json()[0]["kind"] == "switch_connected"
    ingest(client, {"type": "event", "kind": "switch_disconnected", "dpid": "0000000000000002", "t": t + 1})
    sw = {s["dpid"]: s for s in client.get("/api/switches", headers=h).json()}
    assert sw["0000000000000002"]["connected"] is False


def test_bad_and_unknown_records_do_not_crash_ingest(client):
    assert ingest(client, {"type": "nonsense"}) == IGNORED
    assert ingest(client, {"type": "snapshot", "t": time.time()}) == ERROR  # no dpid / table
    assert client.app.state.ingestor.stats["errors"] == 1
    assert ingest(client, alert_rec()) == OK  # still working afterwards


# ---- the ordered spool reader and the acknowledgement ------------------------------------------------------
def test_spool_tail_ingests_in_order_and_acknowledges(client, tokens, settings):
    sp = AlertSpool(settings.spool_path)  # the engine's own spool class
    for i in range(1, 4):
        sp.append(alert_rec(f"{i:032d}", seq=None))
    tail = client.app.state.tail
    assert tail.poll(client.app.state.ingestor.ingest) == 3
    assert sp.acked() == 3, "the engine's spool sees the core's acknowledgement"
    assert sp.unacked() == []
    assert client.get("/api/alerts", headers=bearer(tokens["viewer"])).json()["total"] == 3
    sp.append(alert_rec("9" * 32, seq=None))
    assert tail.poll(client.app.state.ingestor.ingest) == 1 and sp.acked() == 4


def test_spool_tail_resumes_after_restart_without_reingesting(client, settings):
    sp = AlertSpool(settings.spool_path)
    sp.append(alert_rec("1" * 32, seq=None))
    client.app.state.tail.poll(client.app.state.ingestor.ingest)
    fresh = SpoolTail(settings.spool_path, client.app.state.sf)  # what a restarted core would build
    assert fresh.last_seq == 1
    assert fresh.poll(client.app.state.ingestor.ingest) == 0


def test_spool_tail_waits_for_a_half_written_line(client, settings):
    os.makedirs(os.path.dirname(settings.spool_path), exist_ok=True)
    line = json.dumps(dict(alert_rec("7" * 32), seq=1))
    with open(settings.spool_path, "w") as fh:
        fh.write(line[:40])  # the engine is mid-write
    tail = client.app.state.tail
    assert tail.poll(client.app.state.ingestor.ingest) == 0
    with open(settings.spool_path, "a") as fh:
        fh.write(line[40:] + "\n")
    assert tail.poll(client.app.state.ingestor.ingest) == 1


def test_spool_tail_reads_rotated_files_oldest_first(client, settings):
    sp = AlertSpool(settings.spool_path, max_bytes=2048, backups=3)
    for i in range(1, 9):
        sp.append(alert_rec(f"{i:032d}", seq=None, summary="x" * 300))
    assert os.path.exists(settings.spool_path + ".1")
    seen = []
    tail = SpoolTail(settings.spool_path, client.app.state.sf)
    tail.poll(lambda rec, src: seen.append(rec["seq"]) or OK)
    assert seen == sorted(seen) and seen[-1] == 8


def test_ack_never_moves_backwards(tmp_path):
    p = str(tmp_path / "a.ack")
    write_ack(p, 10)
    write_ack(p, 3)
    assert open(p).read() == "10"


# ---- the live ZeroMQ path ----------------------------------------------------------------------------------
def test_zmq_receiver_ingests_live_records(tmp_path):
    ep = f"ipc://{tmp_path}/ev.ipc"
    s = load_settings(data_dir=str(tmp_path / "d"), start_receiver=True, event_endpoint=ep, spool_poll_seconds=0.2)
    with TestClient(create_app(s)) as c:
        c.post("/api/setup", json={"username": "admin", "password": PASSWORDS["admin"]})
        h = bearer(login(c, "admin"))
        push = zmq.Context.instance().socket(zmq.PUSH)
        push.setsockopt(zmq.LINGER, 0)
        push.connect(ep)
        try:
            push.send(json.dumps(alert_rec("5" * 32, seq=None)).encode())
            push.send(b"not json")  # ignored, does not stop the receiver
            push.send(json.dumps(snapshot_rec()).encode())
            deadline = time.time() + 5
            while time.time() < deadline and c.get("/api/alerts", headers=h).json()["total"] < 1:
                time.sleep(0.05)
            assert c.get("/api/alerts", headers=h).json()["total"] == 1
            assert len(c.get("/api/rules", headers=h).json()) == 3
            detail = c.get("/api/health/detail", headers=h).json()
            assert detail["receiver"]["bound"] is True and detail["receiver"]["zmq_records"] >= 2
        finally:
            push.close()


# ---- recordings ------------------------------------------------------------------------------------------------
def test_recording_captures_ingested_records(client, tokens):
    h = bearer(tokens["admin"])
    r = client.post("/api/sessions", json={"name": "demo run 1"}, headers=h)
    assert r.status_code == 201 and r.json()["recording"] is True
    rid = r.json()["id"]
    assert client.post("/api/sessions", json={"name": "second"}, headers=h).status_code == 409
    ingest(client, alert_rec())
    ingest(client, snapshot_rec())
    stopped = client.post(f"/api/sessions/{rid}/stop", headers=h).json()
    assert stopped["records"] == 2 and stopped["recording"] is False
    dl = client.get(f"/api/sessions/{rid}/download", headers=bearer(tokens["analyst"]))
    lines = [json.loads(l) for l in dl.text.splitlines()]
    assert [l["record"]["type"] for l in lines] == ["alert", "snapshot"]
    assert client.post("/api/sessions", json={"name": "../../etc/passwd"}, headers=h).status_code == 422


# ---- dashboard-requested repair --------------------------------------------------------------------------------
def test_repair_request_is_validated_written_for_the_engine_and_audited(client, tokens, settings):
    ingest(client, snapshot_rec())
    h = bearer(tokens["admin"])
    ok_rule = {"dpid": DPID, "table_id": 0, "priority": 100, "match": {"tcp_dst": 23}}
    forged = {"dpid": DPID, "table_id": 0, "priority": 300, "match": {"eth_type": 2054}}
    assert client.post("/api/rules/repair", json=ok_rule, headers=h).status_code == 409   # nothing to repair
    assert client.post("/api/rules/repair", json=dict(forged, priority=301), headers=h).status_code == 404
    assert client.post("/api/rules/repair", json=dict(forged, dpid="../../etc"), headers=h).status_code == 422
    r = client.post("/api/rules/repair", json=forged, headers=h)
    assert r.status_code == 202 and r.json()["status_before"] == "forged"
    rid = r.json()["request_id"]
    path = os.path.join(settings.control_dir, f"repair-{rid}.json")
    req = json.load(open(path))
    assert req == {"request_id": rid, "dpid": DPID, "table_id": 0, "priority": 300, "match": {"eth_type": 2054}, "requested_by": "admin"}
    audit = client.get("/api/audit", params={"action": "rule_repair_requested"}, headers=h).json()
    assert audit["total"] == 1 and audit["items"][0]["details"]["status_before"] == "forged"
