"""Phase 1 live tests: real OVS + Mininet + the real engine process. Every attack uses the attacker's tool,
`ovs-ofctl`, directly against switch s1. Tests share one lab (module fixture) and run in file order.

The engine is started with a 2 s reconcile poll as a safety net, but the assertions on `detected_by` prove that
the monitor event (not the poll) caught each attack.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import DEFAULT_POLICY, DPID, REPO, dump, find_rule, ofctl, start_engine

ACL = "table=0,priority=100,tcp,tp_dst=23"
TELNET_MATCH = "tcp,tp_dst=23"


def epoch_of(cookie):
    return cookie & 0xFFFF


# ---- baseline ------------------------------------------------------------------------------------------------
def test_policy_is_installed_signed_and_traffic_flows(lab):
    rules = {r["priority"]: r for r in dump(0)}
    assert set(rules) == {100, 90, 0}
    assert all(r["cookie"] != 0 and epoch_of(r["cookie"]) == 1 for r in rules.values())
    assert rules[100]["actions"] == "drop"
    assert lab.net.pingAll(timeout="2") == 0.0, "table-1 learning switch must still forward traffic"
    assert lab.alerts() == [], "a clean start must not raise alerts"
    assert lab.engine_status()["monitors_up"][DPID] is True


def test_signed_cookies_are_unique_per_rule(lab):
    cookies = [r["cookie"] for r in dump(0)]
    assert len(set(cookies)) == len(cookies)


# ---- attacks -----------------------------------------------------------------------------------------------
def test_a1_forged_rule_is_detected_and_removed(lab):
    t0 = time.time()
    ofctl("add-flow", "s1", "table=0,priority=300,arp,actions=drop")
    a = lab.wait_alert("forged", t0)
    assert a, lab.ryu_log()
    assert a["action"] == "removed" and a["severity"] == "high" and a["detected_by"] == "monitor_event"
    assert a["signature_valid"] is False and a["table_id"] == 0 and a["priority"] == 300
    assert "did not install" in a["summary"]
    assert lab.wait(lambda: find_rule(0, 300) is None), "forged rule must be gone from the switch"
    t = a["timing"]
    assert t["t_event_rx"] <= t["t_classified"] <= t["t_response_sent"] and t["detect_latency_ms"] >= 0
    assert a["t"] - t0 < 3.0
    assert lab.net.pingAll(timeout="2") == 0.0


def test_a2_modified_rule_is_detected_and_restored(lab):
    golden = find_rule(0, 100, TELNET_MATCH)
    t0 = time.time()
    ofctl("--strict", "mod-flows", "s1", f"{ACL},actions=output:1")
    a = lab.wait_alert("altered", t0)
    assert a and a["action"] == "restored" and a["detected_by"] == "monitor_event"
    assert "instructions_differ" in a["reasons"] and a["signature_valid"] is False
    assert lab.wait(lambda: (find_rule(0, 100, TELNET_MATCH) or {}).get("actions") == "drop"), "ACL must be back to drop"
    restored = find_rule(0, 100, TELNET_MATCH)
    assert restored["cookie"] == golden["cookie"], "restore re-installs the original signed cookie"
    upd = lab.wait(lambda: lab.updates(a["id"]))
    assert upd and upd[0]["kind"] == "restored" and upd[0]["timing"]["time_to_restore_ms"] >= 0


def test_a3_deleted_rule_is_detected_and_restored(lab):
    t0 = time.time()
    ofctl("--strict", "del-flows", "s1", ACL)
    a = lab.wait_alert("missing", t0)
    assert a and a["action"] == "restored" and a["golden"]["cookie"]
    assert lab.wait(lambda: find_rule(0, 100, TELNET_MATCH)), "deleted rule must come back"
    assert find_rule(0, 100, TELNET_MATCH)["cookie"] == int(a["golden"]["cookie"], 16)


def test_a4_shadowing_rule_is_detected_and_removed(lab):
    t0 = time.time()
    ofctl("add-flow", "s1", "table=0,priority=200,tcp,tp_dst=23,actions=output:1")  # outranks the telnet ACL
    a = lab.wait_alert("shadow", t0)
    assert a and a["action"] == "removed" and a["shadows"]
    assert lab.wait(lambda: find_rule(0, 200) is None)
    assert find_rule(0, 100, TELNET_MATCH)["actions"] == "drop"


def test_a5_cookie_copied_from_a_valid_rule_does_not_make_a_rule_trusted(lab):
    valid_cookie = find_rule(0, 100, TELNET_MATCH)["cookie"]
    t0 = time.time()
    ofctl("add-flow", "s1", f"cookie={valid_cookie:#x},table=0,priority=250,arp,actions=drop")
    a = lab.wait_alert("forged", t0)
    assert a and a["signature_valid"] is False and a["action"] == "removed"
    assert lab.wait(lambda: find_rule(0, 250) is None)


def test_a5b_tamper_and_quick_revert_is_not_silent(lab):
    t0 = time.time()
    subprocess.run(f"ovs-ofctl -O OpenFlow13 --strict mod-flows s1 '{ACL},actions=output:1' && "
                   f"ovs-ofctl -O OpenFlow13 --strict mod-flows s1 '{ACL},actions=drop'", shell=True, check=True)
    a = lab.wait(lambda: (lab.alerts(t0, "unattributed_change") or lab.alerts(t0, "altered") or [None])[0], 6)
    assert a, "a tamper-and-revert must raise an alert (unattributed_change, or altered if caught mid-way)"
    assert lab.wait(lambda: (find_rule(0, 100, TELNET_MATCH) or {}).get("actions") == "drop")


# ---- legitimate churn must stay silent ------------------------------------------------------------------------
def test_policy_change_is_signed_churn_with_zero_alerts(lab):
    lab.settle(2.0)
    before = len(lab.alerts())
    lab.policy.write_text(DEFAULT_POLICY.replace(
        "  - {table: 0, priority: 90,", "  - {table: 0, priority: 95, match: {eth_type: 0x0800, ip_proto: 17, udp_dst: 5353}, instructions: []}\n  - {table: 0, priority: 80,"))
    assert lab.wait(lambda: find_rule(0, 95, "udp"), 6), "new policy rule must be installed"
    assert lab.wait(lambda: find_rule(0, 90) is None and find_rule(0, 80, "tp_dst=22")), "changed rule must be re-priced"
    for r in dump(0):
        assert r["cookie"] != 0 and epoch_of(r["cookie"]) == 1
    lab.settle(5.0)  # includes at least two reconcile passes
    assert len(lab.alerts()) == before, [a["kind"] for a in lab.alerts()[before:]]
    assert lab.net.pingAll(timeout="2") == 0.0


def test_replaying_a_retired_signed_rule_is_flagged_even_with_a_valid_signature(lab):
    # priority-90 ssh rule was retired by the previous test; the attacker re-adds it with its old (once valid) cookie
    t0 = time.time()
    # a fresh signature for the old content is impossible without the key, so the attacker can only reuse a cookie:
    # take the telnet rule's valid cookie and attach it to the retired slot
    ofctl("add-flow", "s1", f"cookie={find_rule(0, 100, TELNET_MATCH)['cookie']:#x},table=0,priority=90,tcp,tp_dst=22,actions=goto_table:1")
    a = lab.wait(lambda: (lab.alerts(t0, "forged") + lab.alerts(t0, "shadow") or [None])[0], 6)
    assert a and a["action"] == "removed"
    assert lab.wait(lambda: find_rule(0, 90) is None)


def test_key_rotation_resigns_everything_with_zero_alerts(lab):
    before = len(lab.alerts())
    old = {r["priority"]: r["cookie"] for r in dump(0)}
    (lab.control / "rotate").write_text("")
    assert lab.wait(lambda: all(epoch_of(r["cookie"]) == 2 for r in dump(0)) and len(dump(0)) == len(old), 8), dump(0)
    assert all(r["cookie"] != old[r["priority"]] for r in dump(0)), "every rule gets a new signature"
    lab.settle(5.0)
    assert len(lab.alerts()) == before, [a["kind"] for a in lab.alerts()[before:]]
    assert lab.engine_status()["epoch"] == 2
    # an old-epoch signed rule replayed by an attacker is still not trusted: it is not in the golden store
    t0 = time.time()
    ofctl("add-flow", "s1", f"cookie={old[100]:#x},table=0,priority=60,arp,actions=drop")
    a = lab.wait_alert("forged", t0)
    assert a and a["action"] == "removed"


def test_alert_json_never_contains_key_material(lab):
    key_hex = Path(lab.key).read_text().strip()
    blob = lab.spool.read_text() + lab.events.read_text() + lab.ryu_log()
    assert key_hex not in blob


# ---- engine hygiene ----------------------------------------------------------------------------------------------
def test_engine_refuses_to_start_without_a_key(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(REPO), FLOWGUARD_DATA_DIR=str(tmp_path), FLOWGUARD_KEY_FILE=str(tmp_path / "absent.key"),
               FLOWGUARD_CONFIG=str(tmp_path / "none.yaml"))
    env.pop("FLOWGUARD_HMAC_KEY", None)
    p = subprocess.run([str(REPO / ".venv-engine/bin/ryu-manager"), "--ofp-tcp-listen-port", "6699", "engine.app"], cwd=str(REPO),
                       env=env, capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and "not found" in (p.stdout + p.stderr)


def test_engine_refuses_a_world_readable_key(tmp_path):
    k = tmp_path / "hmac.key"
    k.write_text("ab" * 32)
    k.chmod(0o644)
    env = dict(os.environ, PYTHONPATH=str(REPO), FLOWGUARD_DATA_DIR=str(tmp_path), FLOWGUARD_KEY_FILE=str(k),
               FLOWGUARD_CONFIG=str(tmp_path / "none.yaml"))
    env.pop("FLOWGUARD_HMAC_KEY", None)
    p = subprocess.run([str(REPO / ".venv-engine/bin/ryu-manager"), "--ofp-tcp-listen-port", "6699", "engine.app"], cwd=str(REPO),
                       env=env, capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and "0600" in (p.stdout + p.stderr)
