"""Phase 5 end to end on real OVS + Mininet + the real engine + the core: the L1 finding carries a risk decision and an
L3 score, probe results and scores reach the API, and a policy saved in the core really changes what the engine does."""
import time

import pytest

from conftest import DPID, find_rule, ofctl
from test_core_live import alerts, core, wait

FORGED = "table=0,priority=310,arp,actions=drop"


@pytest.fixture(scope="module", autouse=True)
def fast_probes():
    mp = pytest.MonkeyPatch()
    mp.setenv("FLOWGUARD_PROBE_S", "2")
    yield
    mp.undo()


def policy(actions):
    return {"dry_run": False, "response_mode": "restore", "critical_tables": [0],
            "weights": {"l1": 1.0, "l2": 0.8, "l3": 0.4}, "thresholds": {"alert": 0.3, "restore": 0.5, "quarantine": 0.8},
            "actions": actions}


ALERT_ONLY = {"critical": "alert_only", "high": "alert_only", "medium": "alert_only", "low": "alert_only"}
RESTORE = {"critical": "restore_and_alert", "high": "restore_and_alert", "medium": "restore_and_alert", "low": "alert_only"}


def test_finding_carries_risk_and_l3_score_and_results_reach_the_api(lab):
    with core(lab) as c:
        t0 = time.time()
        ofctl("add-flow", "s1", FORGED)
        a = lab.wait_alert("forged", t0)
        assert a, lab.ryu_log()
        # default policy is a dry run: the decision is recorded but L1's own response still removes the forged rule
        assert a["risk"]["l1"] == 1.0 and a["risk"]["dry_run"] is True and a["risk"]["effective_action"] == "none"
        assert any("not signed" in r for r in a["l3_reasons"])
        assert wait(lambda: c.get("/api/ml/scores").json()["items"], 10), "the L3 score must reach the core"
        ml = c.get("/api/ml/scores").json()
        assert ml["available"] is True and ml["items"][0]["score"] >= 0.6
        probes = wait(lambda: c.get("/api/probes").json() if c.get("/api/probes").json()["items"] else None, 15)
        assert probes and probes["available"] is True and probes["items"][0]["data"]["status"] in ("pass", "fail")
        assert wait(lambda: find_rule(0, 310) is None, 6)


def test_policy_saved_in_the_core_decides_whether_the_engine_repairs(lab):
    with core(lab) as c:
        assert c.put("/api/policies", json=policy(ALERT_ONLY)).status_code == 200
        time.sleep(2.0)  # the engine's watcher picks up control/risk-policy.json
        t0 = time.time()
        ofctl("add-flow", "s1", FORGED)
        a = lab.wait_alert("forged", t0)
        assert a and a["action"] == "none" and a["action_reason"] == "risk_policy_alert_only", a
        time.sleep(3.0)
        assert find_rule(0, 310), "with every action set to alert_only the engine must not remove the rule"
        assert c.put("/api/policies", json=policy(RESTORE)).status_code == 200
        assert lab.wait(lambda: find_rule(0, 310) is None, 12), "once the policy asks for repair, the next pass removes it"
        assert wait(lambda: [x for x in alerts(c, "forged") if x["id"] == a["id"]], 10)


QUARANTINE = {"critical": "quarantine_port", "high": "quarantine_port", "medium": "quarantine_port", "low": "alert_only"}


def test_quarantine_cuts_the_offending_port_and_an_admin_release_restores_it(lab):
    lab.net.pingAll(timeout="1")  # the learning switch must have seen the hosts: only learned host ports can be quarantined
    with core(lab) as c:
        assert c.put("/api/policies", json=policy(QUARANTINE)).status_code == 200
        time.sleep(2.0)
        t0 = time.time()
        ofctl("add-flow", "s1", "table=0,priority=310,in_port=2,actions=drop")  # an unsigned rule bound to port 2 (h2)
        a = lab.wait_alert("port_quarantined", t0, timeout=10)
        assert a and a["priority"] == 65000, lab.ryu_log()
        assert lab.wait(lambda: find_rule(0, 65000), 6), "the signed quarantine rule must be on the switch"
        assert lab.wait(lambda: find_rule(0, 310) is None, 6), "the offending rule is repaired as well"
        h2 = lab.net.get("h2")
        assert "100% packet loss" in h2.cmd("ping -c1 -W1 10.0.0.1"), "traffic from the quarantined port must be dropped"
        time.sleep(3.0)
        assert not [x for x in lab.alerts(t0) if x["kind"] in ("forged", "shadow", "altered") and x["priority"] == 65000], \
            "the quarantine rule is signed, so L1 must treat it as verified"
        listed = wait(lambda: c.get("/api/quarantine").json()["items"], 12)
        assert listed and listed[0]["port"] == 2
        assert c.post("/api/quarantine/release", json={"dpid": DPID, "port": 2}).status_code == 202
        assert lab.wait(lambda: find_rule(0, 65000) is None, 8), "release removes the quarantine rule"
        assert "0% packet loss" in h2.cmd("ping -c2 -W1 10.0.0.1")
        assert wait(lambda: not c.get("/api/quarantine").json()["items"], 12)
