"""Phase 9 resilience on real OVS + Mininet + the real engine: a controller reconnect storm, an engine restart while the switch
is changed behind its back, and load (a large policy, then a flood of unsigned rules). Switch changes use the lab's own
`ovs-ofctl`, the same tool the Phase 1 tests use. Measured numbers are written to results/load.json."""
import json
import subprocess
import time

import pytest

from conftest import DEFAULT_POLICY, DPID, REPO, dump, find_rule, ofctl, start_engine

BAD_KINDS = ("forged", "altered", "missing", "shadow", "unattributed_change")


@pytest.fixture(scope="module", autouse=True)
def fast_probes():
    mp = pytest.MonkeyPatch()
    mp.setenv("FLOWGUARD_PROBE_S", "2")
    yield
    mp.undo()


def counters(lab):
    return lab.engine_status().get("counters", {})


def test_a_controller_reconnect_storm_raises_no_false_alerts_and_the_policy_survives(lab):
    t0 = time.time()
    for _ in range(15):  # make the switch drop and re-open its controller connection again and again (the flow table is kept)
        subprocess.run(["ovs-appctl", "bridge/reconnect", "s1"], capture_output=True)
        time.sleep(0.5)
    ready = lab.wait(lambda: lab.engine_status().get("ready", {}).get(DPID), timeout=30)
    assert ready, lab.ryu_log()
    before = counters(lab).get("probes", 0)
    assert lab.wait(lambda: counters(lab).get("probes", 0) >= before + 2, timeout=30), "probes must resume after the storm"
    bad = [a for a in lab.alerts(t0) if a["kind"] in BAD_KINDS]
    assert not bad, [(a["kind"], a.get("detected_by"), a.get("priority")) for a in bad]  # a reconnect is not tampering
    rules = {r["priority"]: r for r in dump(0)}
    assert set(rules) == {100, 90, 0} and rules[100]["actions"] == "drop"
    assert lab.net.pingAll(timeout="2") == 0.0


def test_a_switch_whose_flow_table_was_wiped_is_reported_missing_and_repaired(lab):
    t0 = time.time()
    # removing the controller makes Open vSwitch fall back to standalone mode, which wipes its own flow table
    subprocess.run(["ovs-vsctl", "del-controller", "s1"], capture_output=True)
    time.sleep(1.0)
    subprocess.run(["ovs-vsctl", "set-controller", "s1", "tcp:127.0.0.1:6653", "ptcp:6634"], capture_output=True)
    assert lab.wait_alert("missing", t0, timeout=30), lab.ryu_log()
    a = lab.alerts(t0, "missing")[0]
    assert a["detected_by"] == "connect_audit" and a["action"] == "restored"
    assert lab.wait(lambda: {r["priority"] for r in dump(0)} == {100, 90, 0}, timeout=20), "the signed rules must be back"
    assert lab.wait(lambda: lab.engine_status().get("ready", {}).get(DPID), timeout=30)
    assert lab.net.pingAll(timeout="2") == 0.0


def test_changes_made_while_the_engine_is_down_are_found_and_repaired_after_it_restarts(lab):
    lab.ryu.terminate()
    lab.ryu.wait(timeout=10)
    t0 = time.time()
    ofctl("add-flow", "s1", "table=0,priority=350,arp,actions=drop")                        # forged while nobody is watching
    ofctl("--strict", "mod-flows", "s1", "table=0,priority=100,tcp,tp_dst=23,actions=output:1")  # altered while nobody is watching
    time.sleep(1.0)
    lab.ryu = start_engine(lab.data, lab.policy, lab.key)
    assert lab.wait_alert("forged", t0, timeout=40), lab.ryu_log()
    assert lab.wait_alert("altered", t0, timeout=20), lab.ryu_log()
    assert lab.wait(lambda: find_rule(0, 350) is None, 10), "the forged rule must be removed"
    assert lab.wait(lambda: (find_rule(0, 100, "tcp,tp_dst=23") or {}).get("actions") == "drop", 10), "the altered rule must be restored"
    assert lab.wait(lambda: lab.engine_status().get("ready", {}).get(DPID), timeout=30)
    assert lab.net.pingAll(timeout="2") == 0.0


def test_a_large_policy_converges_and_tampering_is_still_detected_quickly(lab):
    n = 300
    t0 = time.time()
    extra = "".join(f"  - {{table: 0, priority: {400 + i}, match: {{eth_type: 0x0800, ip_proto: 6, tcp_dst: {1000 + i}}}, instructions: []}}\n" for i in range(n))
    lab.policy.write_text(DEFAULT_POLICY + extra)
    assert lab.wait(lambda: len(dump(0)) >= n + 3, timeout=60), f"only {len(dump(0))} rules installed"
    converge_s = round(time.time() - t0, 2)
    time.sleep(3)
    assert not [a for a in lab.alerts(t0) if a["kind"] in BAD_KINDS], "installing a large policy is legitimate churn"
    before = counters(lab).get("probes", 0)
    assert lab.wait(lambda: counters(lab).get("probes", 0) >= before + 2, timeout=60), "probes must keep running with 300 rules"
    t1 = time.time()
    ofctl("--strict", "mod-flows", "s1", "table=0,priority=500,tcp,tp_dst=1100,actions=output:1")
    a = lab.wait_alert("altered", t1, timeout=10)
    assert a, lab.ryu_log()
    detect_ms = round((a["t"] - t1) * 1000, 1)
    assert lab.wait(lambda: (find_rule(0, 500, "tp_dst=1100") or {}).get("actions") == "drop", 10)
    assert lab.net.pingAll(timeout="2") == 0.0
    (REPO / "results").mkdir(exist_ok=True)
    (REPO / "results" / "load.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "rules_in_policy": n + 3, "converge_seconds": converge_s,
        "altered_rule_wall_clock_ms": detect_ms, "probe_cycles": counters(lab).get("probes"), "failed_probe_cycles": counters(lab).get("probe_fails", 0),
        "environment": "one Open vSwitch switch, Mininet, WSL2"}, indent=2))


def test_a_flood_of_unsigned_rules_is_removed_at_a_bounded_rate_and_the_engine_stays_up(lab):
    time.sleep(62)  # let the per-minute repair budget of the earlier tests expire
    flood = lab.data / "flood.flows"
    flood.write_text("".join(f"table=0,priority={5000 + i},tcp,tp_dst={20000 + i},actions=drop\n" for i in range(45)))
    t0 = time.time()
    ofctl("add-flows", "s1", str(flood))
    assert lab.wait(lambda: len([r for r in dump(0) if r["priority"] >= 5000]) < 45, timeout=20), "removal must start"
    time.sleep(12)
    left = len([r for r in dump(0) if r["priority"] >= 5000])
    assert left < 45, "rules must be getting removed"
    assert lab.alerts(t0, "restore_rate_limited"), "the per-minute repair limit (anti-loop) must say it is holding back"
    status = lab.engine_status()
    assert time.time() - status["t"] < 5, "the engine must still be reporting"
    assert lab.wait(lambda: not [r for r in dump(0) if r["priority"] >= 5000], timeout=120), "the rest goes in the next minute"
    assert lab.net.pingAll(timeout="2") == 0.0
