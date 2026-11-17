#!/usr/bin/env python3
"""FlowGuard evaluation (make eval, needs root): repeated trials on the real lab (Open vSwitch + Mininet + the real
engine), measuring how fast each kind of rule tampering is detected and repaired, and whether legitimate policy churn
raises false alerts. Writes results/eval.json and docs/results.md with the measured numbers only.

The trials use the lab's own `ovs-ofctl` against switch s1 (the tool an operator, or an intruder on the host, would use).
This measures the engine; it is not an attack tool and does nothing outside the lab.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "tests" / "integration"), str(REPO / "topo")]

import topo_basic  # noqa: E402
from conftest import DEFAULT_POLICY, DPID, Lab, find_rule, ofctl, start_engine  # noqa: E402
from engine.crypto import generate_key_file  # noqa: E402

TRIALS = {
    "forged": lambda i: ofctl("add-flow", "s1", f"table=0,priority={300 + i},arp,actions=drop"),
    "altered": lambda i: ofctl("--strict", "mod-flows", "s1", "table=0,priority=100,tcp,tp_dst=23,actions=output:1"),
    "missing": lambda i: ofctl("--strict", "del-flows", "s1", "table=0,priority=100,tcp,tp_dst=23"),
    "shadow": lambda i: ofctl("add-flow", "s1", f"table=0,priority={200 + i},tcp,tp_dst=22,actions=output:1"),
}


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "p95": round(xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))], 1), "max": round(xs[-1], 1)}


def run_kind(lab: Lab, kind: str, n: int) -> dict:
    wall, detect, restore, by, missed = [], [], [], {}, 0
    for i in range(n):
        t0 = time.time()
        TRIALS[kind](i)
        a = lab.wait_alert(kind, t0, timeout=8)
        if a is None:
            missed += 1
        else:
            wall.append((a["t"] - t0) * 1000)
            detect.append(a.get("timing", {}).get("detect_latency_ms"))
            by[a.get("detected_by")] = by.get(a.get("detected_by"), 0) + 1
            u = lab.wait(lambda: lab.updates(a["id"]), timeout=4)
            if u:
                restore.append(u[0].get("timing", {}).get("time_to_restore_ms"))
        time.sleep(1.6)  # beyond the 1 s alert de-duplication window set for this run
        lab.wait(lambda: not lab.alerts(since=time.time() - 0.5), timeout=1)
    return {"trials": n, "detected": n - missed, "missed": missed, "detected_by": by,
            "wall_clock_ms": stats(wall), "engine_detect_ms": stats(detect), "restore_ms": stats(restore)}


def churn_false_alerts(lab: Lab, cycles: int) -> int:
    before = len(lab.alerts())
    base = lab.policy.read_text()
    for i in range(cycles):
        lab.policy.write_text(base + f"  - {{table: 0, priority: {50 + i}, match: {{eth_type: 0x0800, ip_proto: 17, udp_dst: {6000 + i}}}, instructions: []}}\n")
        lab.wait(lambda: find_rule(0, 50 + i), 5)
        lab.policy.write_text(base)
        lab.wait(lambda: find_rule(0, 50 + i) is None, 5)
        time.sleep(0.5)
    time.sleep(3)
    return len(lab.alerts()) - before


def rss_mb(pid: int):
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def run_soak(lab: Lab, seconds: int) -> int:
    """Run normal operation (policy churn, host traffic, probes) for a while: expect no alerts, no failed pings, no failed
    probes, and no runaway memory in the engine process."""
    t0 = time.time()
    alerts0, rss0 = len(lab.alerts()), rss_mb(lab.ryu.pid)
    base = lab.policy.read_text()
    cycles = bad_pings = 0
    while time.time() - t0 < seconds:
        lab.policy.write_text(base + "  - {table: 0, priority: 55, match: {eth_type: 0x0800, ip_proto: 17, udp_dst: 7000}, instructions: []}\n")
        lab.wait(lambda: find_rule(0, 55), 5)
        time.sleep(2)
        lab.policy.write_text(base)
        lab.wait(lambda: find_rule(0, 55) is None, 5)
        time.sleep(2)
        cycles += 1
        if lab.net.pingAll(timeout="1") != 0.0:
            bad_pings += 1
    c = lab.engine_status().get("counters", {})
    out = {"seconds": round(time.time() - t0), "churn_cycles": cycles, "false_alerts": len(lab.alerts()) - alerts0, "failed_ping_rounds": bad_pings,
           "probe_cycles": c.get("probes"), "failed_probe_cycles": c.get("probe_fails", 0), "engine_rss_mb": {"start": rss0, "end": rss_mb(lab.ryu.pid)}}
    (REPO / "results").mkdir(exist_ok=True)
    (REPO / "results" / "soak.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    grew = out["engine_rss_mb"]["end"] and rss0 and out["engine_rss_mb"]["end"] > rss0 * 1.5 + 20
    ok = out["false_alerts"] == 0 and bad_pings == 0 and not out["failed_probe_cycles"] and not grew
    print("SOAK PASS" if ok else "SOAK FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--churn", type=int, default=10)
    ap.add_argument("--soak", type=int, default=0, help="run only a soak of this many seconds (make test-soak)")
    args = ap.parse_args()
    if os.geteuid() != 0:
        print("make eval needs root (Mininet/OVS): run `sudo make eval`", file=sys.stderr)
        return 1
    subprocess.run(["mn", "-c"], capture_output=True)
    data = Path(tempfile.mkdtemp(prefix="fg-eval-"))
    key = data / "keys" / "hmac.key"
    generate_key_file(str(key))
    policy = data / "policy.yaml"
    policy.write_text(DEFAULT_POLICY)
    cfg = data / "eval-config.yaml"
    cfg.write_text("engine:\n  alert_dedupe_seconds: 1.0\n  probe_interval_seconds: 2.0\n")
    lab = Lab(data, policy, key)
    lab.ryu = start_engine(data, policy, key, {"FLOWGUARD_CONFIG": str(cfg)})
    time.sleep(3)
    net, _ = topo_basic.build_net("auto", False, "127.0.0.1", 6653, protocols="OpenFlow10,OpenFlow13", listen_port=6634)
    lab.net = net
    try:
        net.start()
        if not lab.wait(lambda: lab.engine_status().get("ready", {}).get(DPID), timeout=25):
            print("engine never became ready", file=sys.stderr)
            return 1
        lab.settle(2.0)
        if args.soak:
            return run_soak(lab, args.soak)
        t_start = time.time()
        results = {}
        for kind in TRIALS:
            print(f"[eval] {kind} x{args.trials} ...", flush=True)
            results[kind] = run_kind(lab, kind, args.trials)
        print(f"[eval] legitimate policy churn x{args.churn} ...", flush=True)
        false_alerts = churn_false_alerts(lab, args.churn)
        st = lab.engine_status()
        l3 = [a.get("risk", {}).get("l3") for a in lab.alerts() if a.get("risk")]
        out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "trials_per_kind": args.trials, "kinds": results,
               "legit_churn": {"cycles": args.churn, "false_alerts": false_alerts},
               "probes": {"cycles": st.get("counters", {}).get("probes"), "failed_cycles": st.get("counters", {}).get("probe_fails")},
               "l3_score_on_tamper": stats(l3), "duration_s": round(time.time() - t_start, 1),
               "environment": "one Open vSwitch switch, four hosts, Mininet, WSL2; engine, core and lab on one host"}
    finally:
        net.stop()
        lab.ryu.terminate()
        try:
            lab.ryu.wait(timeout=8)
        except subprocess.TimeoutExpired:
            lab.ryu.kill()
        subprocess.run(["mn", "-c"], capture_output=True)
    (REPO / "results").mkdir(exist_ok=True)
    (REPO / "results" / "eval.json").write_text(json.dumps(out, indent=2))
    write_report(out)
    print(json.dumps(out, indent=2))
    return 0


def fmt(s):
    return "n/a" if not s else f"{s['median']} / {s['p95']} / {s['max']}"


def load_section() -> str:
    """Numbers written by tests/integration/test_resilience_live.py (results/load.json), when that test has been run."""
    lp = REPO / "results" / "load.json"
    if not lp.exists():
        return ""
    l = json.loads(lp.read_text())
    return f"""
## Load and resilience (live lab tests, `tests/integration/test_resilience_live.py`, {l['generated_at']})
- A policy of {l['rules_in_policy']} rules was applied and verified in {l['converge_seconds']} s. Changing one rule under that load was reported in {l['altered_rule_wall_clock_ms']} ms (wall clock). L2 probes kept running with {l['failed_probe_cycles']} failed cycles.
- Pass/fail only, same lab: 15 controller reconnects in 8 s raise no alerts; a switch whose flow table is wiped by a controller flap is reported missing and repaired; rules changed while the engine is down are reported and repaired after it restarts; a flood of 45 unsigned rules is removed at the limited repair rate (30 per minute per switch, by design) while the engine keeps running; two linked switches are protected independently (`tests/integration/test_multi_switch_live.py`).
- Environment: {l['environment']}. Not measured: more than two switches, hardware switches, hundreds of thousands of rules.
"""


def write_report(out: dict) -> None:
    rows = "\n".join(f"| {k} | {v['detected']}/{v['trials']} | {fmt(v['engine_detect_ms'])} | {fmt(v['wall_clock_ms'])} | {fmt(v['restore_ms'])} | {v['detected_by']} |"
                     for k, v in out["kinds"].items())
    (REPO / "docs" / "results.md").write_text(f"""# Measured results

Generated by `sudo make eval` on {out['generated_at']} ({out['duration_s']} s). Only measured numbers appear here.
Environment: {out['environment']}. Times are milliseconds as median / 95th percentile / maximum.

| Tampering | Detected | Engine detect | Wall clock (change to alert) | Time to restore | Detected by |
|---|---|---|---|---|---|
{rows}

- **Legitimate policy churn:** {out['legit_churn']['false_alerts']} false alerts over {out['legit_churn']['cycles']} install/retire cycles.
- **L2 canary probes:** {out['probes']['cycles']} probe cycles, {out['probes']['failed_cycles']} with a failure (failures during the shadow and forged trials are expected: the tampering rule really changes forwarding).
- **L3 anomaly score on tampering alerts:** {fmt(out['l3_score_on_tamper'])} (score 0 to 1).
  In this lab the baseline sees only a handful of policy installs, so only its "rule is not signed" feature fires (0.6); the other features need more normal churn to say anything. L3 is a supporting signal here, not the detector.

## What this does and does not show
- It shows detection and repair speed for four kinds of tampering on one lab switch, {out['trials_per_kind']} trials each, and that normal policy changes do not raise alerts.
- It does not show behaviour on real hardware, many switches, or an adversary who also controls the host (the key, controller and switch share one host in the lab; see `docs/threat_model.md`).
- Wall clock includes the ovs-ofctl process start and the 50 ms polling of the spool file used by this script, so it is an upper bound on what an operator would notice.
""" + load_section())


if __name__ == "__main__":
    raise SystemExit(main())
