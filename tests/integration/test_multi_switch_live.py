"""Phase 9, more than one switch: two real Open vSwitch switches (s1 and s2, linked) under one engine. Each switch is protected
with its own signed rules, a change on one is attributed to that switch only, simultaneous changes on both are both found,
and L2 probes run per switch. Changes use the lab's own `ovs-ofctl`, like the other live tests."""
import subprocess
import time

import pytest

from conftest import DEFAULT_POLICY, Lab, _need_root, ofctl, start_engine

D1, D2 = "0000000000000001", "0000000000000002"


@pytest.fixture(scope="module", autouse=True)
def fast_probes():
    mp = pytest.MonkeyPatch()
    mp.setenv("FLOWGUARD_PROBE_S", "2")
    yield
    mp.undo()


@pytest.fixture(scope="module")
def lab2(tmp_path_factory):
    _need_root()
    import topo_basic
    from engine.crypto import generate_key_file
    subprocess.run(["mn", "-c"], capture_output=True)
    data = tmp_path_factory.mktemp("fgdata2")
    key = data / "keys" / "hmac.key"
    generate_key_file(str(key))
    policy = data / "policy.yaml"
    policy.write_text(DEFAULT_POLICY)
    lab = Lab(data, policy, key)
    lab.ryu = start_engine(data, policy, key)
    time.sleep(3)
    net, _ = topo_basic.build_net("auto", True, "127.0.0.1", 6653, protocols="OpenFlow10,OpenFlow13", listen_port=6634)
    lab.net = net
    try:
        net.start()
        ready = lab.wait(lambda: all(lab.engine_status().get("ready", {}).get(d) for d in (D1, D2)), timeout=40)
        if not ready:
            pytest.fail(f"both switches never became ready\n{lab.ryu_log()}")
        lab.settle(1.5)
        yield lab
    finally:
        net.stop()
        lab.ryu.terminate()
        try:
            lab.ryu.wait(timeout=8)
        except subprocess.TimeoutExpired:
            lab.ryu.kill()
        subprocess.run(["mn", "-c"], capture_output=True)


def table0(sw):
    return ofctl("dump-flows", sw, "table=0")


def test_both_switches_are_protected_with_their_own_signed_rules(lab2):
    for sw in ("s1", "s2"):
        rules = [ln for ln in table0(sw).splitlines() if "priority=" in ln]
        assert len(rules) == 3 and all("cookie=0x0," not in r for r in rules), (sw, rules)
    assert lab2.engine_status()["golden_rules"] == 6
    assert lab2.net.pingAll(timeout="2") == 0.0, "hosts on both switches must reach each other"
    assert not lab2.alerts(), "a clean start on two switches raises nothing"


def test_a_change_on_one_switch_is_attributed_to_that_switch_only(lab2):
    t0 = time.time()
    ofctl("--strict", "mod-flows", "s2", "table=0,priority=100,tcp,tp_dst=23,actions=output:1")
    a = lab2.wait_alert("altered", t0, timeout=10)
    assert a and a["dpid"] == D2 and a["action"] == "restored", lab2.ryu_log()
    assert lab2.wait(lambda: "actions=drop" in [ln for ln in table0("s2").splitlines() if "tp_dst=23" in ln][0], 10)
    assert not [x for x in lab2.alerts(t0) if x["dpid"] == D1], "s1 was not touched"


def test_simultaneous_changes_on_both_switches_are_both_found_and_repaired(lab2):
    time.sleep(2)
    t0 = time.time()
    ofctl("add-flow", "s1", "table=0,priority=310,arp,actions=drop")
    ofctl("--strict", "del-flows", "s2", "table=0,priority=90,tcp,tp_dst=22")
    forged = lab2.wait_alert("forged", t0, timeout=10)
    missing = lab2.wait_alert("missing", t0, timeout=10)
    assert forged and forged["dpid"] == D1 and missing and missing["dpid"] == D2
    assert lab2.wait(lambda: "priority=310" not in table0("s1"), 10)
    assert lab2.wait(lambda: "tp_dst=22" in table0("s2"), 10)
    assert lab2.net.pingAll(timeout="2") == 0.0


def test_l2_probes_run_and_pass_on_every_switch(lab2):
    assert lab2.wait(lambda: set(lab2.engine_status().get("l2", {})) >= {D1, D2}, timeout=30), lab2.engine_status().get("l2")
    assert lab2.wait(lambda: all(v == 0.0 for v in lab2.engine_status()["l2"].values()), timeout=20), lab2.engine_status()["l2"]
