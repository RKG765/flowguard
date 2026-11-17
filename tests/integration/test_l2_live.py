"""Phase 5 live tests (L2 canary probes) on real OVS + Mininet + the real engine, run in alert_only mode so the engine
does not repair anything while a test looks at the result. The only switch interaction is the lab's own `ovs-ofctl`
against s1 (the same tool the Phase 1 tests use)."""
import time

import pytest

from conftest import DPID, ofctl

TELNET = "table=0,priority=300,tcp,tp_dst=23"


@pytest.fixture(scope="module", autouse=True)
def fast_probes_alert_only():
    mp = pytest.MonkeyPatch()
    mp.setenv("FLOWGUARD_PROBE_S", "2")
    mp.setenv("FLOWGUARD_RESPONSE_MODE", "alert_only")
    yield
    mp.undo()


def counters(lab):
    return lab.engine_status().get("counters", {})


def test_healthy_switch_passes_every_canary_probe(lab):
    assert lab.wait(lambda: counters(lab).get("probes", 0) >= 2, timeout=20), lab.ryu_log()
    assert counters(lab).get("probe_fails", 0) == 0
    assert lab.engine_status()["l2"][DPID] == 0.0
    assert not lab.alerts(kind="probe_failed")
    assert lab.net.pingAll(timeout="2") == 0.0, "probes must not disturb host traffic"


def test_a_rule_that_no_longer_acts_as_signed_fails_the_probe_even_though_it_is_still_listed(lab):
    t0 = time.time()
    # an unsigned higher-priority rule takes the telnet traffic: the signed drop rule is still in the table, but
    # packets no longer hit it, which only a data-plane probe can see
    ofctl("add-flow", "s1", TELNET + ",actions=output:1")
    a = lab.wait_alert("probe_failed", t0, timeout=15)
    assert a, lab.ryu_log()
    assert a["layer"] == "L2" and a["detected_by"] == "canary_probe" and a["priority"] == 100
    assert "forwarding differs" in a["summary"]
    assert lab.wait(lambda: lab.engine_status().get("l2", {}).get(DPID) == 1.0, timeout=5)  # status file refreshes once a second


def test_probe_recovers_once_the_rule_is_removed(lab):
    ofctl("--strict", "del-flows", "s1", TELNET)
    assert lab.wait(lambda: lab.engine_status().get("l2", {}).get(DPID) == 0.0, timeout=15), lab.ryu_log()


def n_packets(priority):
    import re
    for line in ofctl("dump-flows", "s1", "table=0").splitlines():
        m = re.search(rf"n_packets=(\d+).*?priority={priority}[, ]", line)
        if m:
            return int(m.group(1))
    return None


def test_probes_exercise_icmp_arp_ipv6_in_port_and_masked_rules_without_false_alarms(lab):
    extra = """\
  - {table: 0, priority: 80, match: {eth_type: 0x0800, ip_proto: 1, ipv4_dst: 10.99.0.0/16}, instructions: []}
  - {table: 0, priority: 70, match: {eth_type: 0x0806, arp_tpa: 10.99.0.1}, instructions: []}
  - {table: 0, priority: 60, match: {in_port: 4, eth_type: 0x0800, ip_proto: 6, tcp_dst: 2222}, instructions: []}
  - {table: 0, priority: 55, match: {eth_type: 0x86dd, ip_proto: 17, udp_dst: 5353}, instructions: []}
"""
    lab.policy.write_text(lab.policy.read_text() + extra)
    assert lab.wait(lambda: all(n_packets(p) is not None for p in (80, 70, 60, 55)), 8), "new signed rules must be installed"
    before = counters(lab).get("probes", 0)
    assert lab.wait(lambda: counters(lab).get("probes", 0) >= before + 3, timeout=25), lab.ryu_log()
    for p in (80, 70, 60, 55):  # every new rule was really hit by its own canary
        assert n_packets(p) >= 3, f"priority {p} was never exercised"
    assert counters(lab).get("probe_fails", 0) == 1, "only the earlier deliberate shadowing test may have failed a probe"
    assert lab.engine_status()["l2"][DPID] == 0.0
    assert lab.net.pingAll(timeout="2") == 0.0
