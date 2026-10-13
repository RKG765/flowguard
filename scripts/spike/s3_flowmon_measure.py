#!/usr/bin/env python3
"""Spike S3/S4: Ryu learning switch + table layout + flow-monitor and polling detection latency.

Run as root with the core venv (it sees the apt Mininet):
    .venv-core/bin/python scripts/spike/s3_flowmon_measure.py --mode of14|nxst13 [--trials 10] [--poll 0.5]

For every trial it performs a real change on the switch with `ovs-ofctl` (the attacker's tool),
then compares when (a) the flow monitor and (b) the table-0 poller noticed it. Wall-clock times come
from the same host so they are directly comparable. Output: docs/spike_evidence/s3_<mode>.json
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "topo"))
import topo_basic  # noqa: E402

BR = "s1"
ACL = "table=0,priority=100,tcp,tp_dst=23"


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def read_log(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def first_monitor_after(rows, t0, table_id, priority, events=None, needle=None):
    """First monitor event after t0 for `table_id`. The OF1.0 NXST text format omits priority, so the
    ofctl_monitor rows are matched on a substring (`needle`) of the printed match instead."""
    for r in rows:
        if r["kind"] != "monitor" or r.get("t_rx", 0) < t0 or r.get("table_id") != table_id:
            continue
        if r.get("priority") is not None and r["priority"] != priority:
            continue
        if r.get("priority") is None and needle and needle not in r.get("match", ""):
            continue
        if events is None or r.get("event") in events:
            return r["t_rx"]
    return None


def start_ofctl_monitor(target, log_path):
    """Run `ovs-ofctl monitor` (OpenFlow 1.0 + Nicira NXST_FLOW_MONITOR) and append each event to the log."""
    import re
    import threading
    proc = subprocess.Popen(["stdbuf", "-oL", "-eL", "ovs-ofctl", "monitor", target, "watch:"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    pat = re.compile(r"event=(\w+)(?: reason=\w+)? table=(\d+) cookie=(0x[0-9a-f]+|[0-9]+) ?(.*)")

    def reader():
        with open(log_path, "a", buffering=1) as f:
            for line in proc.stdout:
                now = time.time()
                m = pat.search(line)
                if m:
                    f.write(json.dumps({"kind": "monitor", "mode": "ofctl_monitor", "t_rx": now,
                                        "event": m.group(1).lower(), "table_id": int(m.group(2)),
                                        "cookie": m.group(3), "priority": None, "match": m.group(4).strip()}) + "\n")
                else:
                    f.write(json.dumps({"kind": "monitor_other", "t": now, "line": line.strip()}) + "\n")

    threading.Thread(target=reader, daemon=True).start()
    return proc


def first_poll_change_after(rows, t0, baseline):
    for r in rows:
        if r["kind"] == "poll" and r["t_recv"] >= t0 and r["digest"] != baseline:
            return r["t_recv"]
    return None


def latest_digest_before(rows, t):
    d = None
    for r in rows:
        if r["kind"] == "poll" and r["t_recv"] <= t:
            d = r["digest"]
    return d


def run_trial(name, of_flag, steps, log, settle):
    """steps: list of ovs-ofctl argument lists executed back-to-back. Returns trial dict."""
    time.sleep(settle)
    base = latest_digest_before(read_log(log), time.time())
    t0 = time.time()
    rcs = []
    for s in steps:
        rcs.append(sh(["ovs-ofctl", "-O", of_flag, *s]).returncode)
    t1 = time.time()
    time.sleep(settle)
    rows = read_log(log)
    return {"trial": name, "t0": t0, "cmd_duration_ms": round((t1 - t0) * 1000, 1), "rcs": rcs, "baseline": base,
            "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["of14", "nxst13", "ofctl_monitor"], required=True)
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--datapath", default="auto")
    ap.add_argument("--tag", default="", help="suffix for evidence file names")
    args = ap.parse_args()
    of_flag = "OpenFlow14" if args.mode == "of14" else "OpenFlow13"
    app_mode = "of13" if args.mode == "ofctl_monitor" else args.mode
    out_dir = REPO / "docs" / "spike_evidence"
    log = f"/tmp/fg_spike_{args.mode}.jsonl"
    ryu_log = out_dir / f"s3_{args.mode}{args.tag}_ryu.log"
    Path(log).unlink(missing_ok=True)

    sh(["mn", "-c"])
    env = dict(os.environ, FG_SPIKE_MODE=app_mode, FG_SPIKE_LOG=log, FG_SPIKE_POLL=str(args.poll))
    ryu = subprocess.Popen([str(REPO / ".venv-engine/bin/ryu-manager"), "--ofp-tcp-listen-port", "6653",
                            str(REPO / "scripts/spike/ryu_spike_app.py")], env=env,
                           stdout=open(ryu_log, "w"), stderr=subprocess.STDOUT)
    summary = {"mode": args.mode, "poll_interval_s": args.poll, "of_flag": of_flag}
    net = None
    mon = None
    try:
        time.sleep(3)
        proto = {"of14": "OpenFlow14", "nxst13": "OpenFlow13", "ofctl_monitor": "OpenFlow10,OpenFlow13"}[args.mode]
        listen = 6634 if args.mode == "ofctl_monitor" else None
        net, info = topo_basic.build_net(args.datapath, False, "127.0.0.1", 6653, protocols=proto, listen_port=listen)
        net.start()
        summary["topology"] = info
        summary["controller_connected"] = topo_basic.wait_controller_connected(["s1"], 20)
        time.sleep(2)
        if args.mode == "ofctl_monitor":
            mon = start_ofctl_monitor("tcp:127.0.0.1:6634", log)
            time.sleep(1.5)
        loss = net.pingAll(timeout="2")
        summary["pingall_loss_percent"] = loss
        flows = sh(["ovs-ofctl", "-O", of_flag, "dump-flows", BR]).stdout
        (out_dir / f"s3_{args.mode}{args.tag}_dump_flows.txt").write_text(flows)
        summary["tables_in_dump"] = sorted({int(l.split("table=")[1].split(",")[0]) for l in flows.splitlines() if "table=" in l})
        time.sleep(1)
        rows = read_log(log)
        summary["log_kinds"] = {k: sum(1 for r in rows if r["kind"] == k) for k in {r["kind"] for r in rows}}
        poll_rows = [r for r in rows if r["kind"] == "poll"]
        summary["poll_tables_seen"] = sorted({t for r in poll_rows for t in r["tables"]})
        summary["poll_rtt_ms_median"] = round(statistics.median(r["rtt_ms"] for r in poll_rows if r["rtt_ms"]), 2) if poll_rows else None
        summary["initial_monitor_events"] = sum(1 for r in rows if r["kind"] == "monitor" and r["event"] in (0, "added", "initial"))
        summary["monitor_other_lines"] = [r["line"] for r in rows if r["kind"] == "monitor_other"][:6]

        acl_n, forged_n = "tp_dst=23", "nw_dst=10.0.0.3"
        scenarios = {
            "modify_acl": ([["--strict", "mod-flows", BR, f"{ACL},actions=output:1"]], 100, {3, "modified"}, acl_n),
            "revert_acl": ([["--strict", "mod-flows", BR, f"{ACL},actions=drop"]], 100, {3, "modified"}, acl_n),
            "add_forged": ([["add-flow", BR, "table=0,priority=300,ip,nw_dst=10.0.0.3,actions=drop"]], 300, {1, "added"}, forged_n),
            "delete_forged": ([["--strict", "del-flows", BR, "table=0,priority=300,ip,nw_dst=10.0.0.3"]], 300, {2, "deleted"}, forged_n),
            "delete_acl": ([["--strict", "del-flows", BR, ACL]], 100, {2, "deleted"}, acl_n),
            "restore_acl": ([["add-flow", BR, f"{ACL},actions=drop"]], 100, {1, "added"}, acl_n),
            "tamper_and_quick_revert": (
                [["--strict", "mod-flows", BR, f"{ACL},actions=output:1"], ["--strict", "mod-flows", BR, f"{ACL},actions=drop"]],
                100, {3, "modified"}, acl_n),
        }
        results = []
        for name, (steps, prio, evs, needle) in scenarios.items():
            lat_mon, lat_poll, detail = [], [], []
            n = 1 if name in ("delete_acl", "restore_acl", "delete_forged") else args.trials
            for i in range(n):
                tr = run_trial(name, of_flag, steps, log, settle=args.poll * 2 + 0.3)
                rows = tr.pop("rows")
                t0 = tr["t0"]
                m = first_monitor_after(rows, t0, 0, prio, evs, needle)
                p = first_poll_change_after(rows, t0, tr["baseline"])
                # for quick-revert the poll sees "no change" when it misses the window; the digest returns to baseline
                if name == "tamper_and_quick_revert":
                    p = None
                    for r in rows:
                        if r["kind"] == "poll" and t0 <= r["t_recv"] <= t0 + tr["cmd_duration_ms"] / 1000 + 0.05 and r["digest"] != tr["baseline"]:
                            p = r["t_recv"]
                            break
                lat_mon.append(None if m is None else round((m - t0) * 1000, 2))
                lat_poll.append(None if p is None else round((p - t0) * 1000, 2))
                detail.append({"cmd_ms": tr["cmd_duration_ms"], "rcs": tr["rcs"]})
                if name == "modify_acl" and i < n - 1:  # put the rule back between repetitions
                    sh(["ovs-ofctl", "-O", of_flag, "--strict", "mod-flows", BR, f"{ACL},actions=drop"])
                if name == "add_forged" and i < n - 1:
                    sh(["ovs-ofctl", "-O", of_flag, "--strict", "del-flows", BR, "table=0,priority=300,ip,nw_dst=10.0.0.3"])
                if name == "revert_acl" and i < n - 1:
                    sh(["ovs-ofctl", "-O", of_flag, "--strict", "mod-flows", BR, f"{ACL},actions=output:1"])
            ok = lambda xs: [x for x in xs if x is not None]
            results.append({
                "scenario": name, "n": n,
                "monitor_detected": len(ok(lat_mon)), "monitor_ms": lat_mon,
                "monitor_ms_median": statistics.median(ok(lat_mon)) if ok(lat_mon) else None,
                "poll_detected": len(ok(lat_poll)), "poll_ms": lat_poll,
                "poll_ms_median": statistics.median(ok(lat_poll)) if ok(lat_poll) else None,
                "ofctl_cmd_ms_median": statistics.median(d["cmd_ms"] for d in detail),
            })
        summary["scenarios"] = results
        rc = 0
    except Exception as exc:  # keep whatever evidence we have
        summary["error"] = repr(exc)
        rc = 1
    finally:
        if mon:
            mon.terminate()
        if net:
            net.stop()
        ryu.terminate()
        try:
            ryu.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ryu.kill()
        sh(["mn", "-c"])
    (out_dir / f"s3_{args.mode}{args.tag}.json").write_text(json.dumps(summary, indent=2))
    Path(log).replace(out_dir / f"s3_{args.mode}{args.tag}_events.jsonl")
    print(json.dumps({k: v for k, v in summary.items() if k != "scenarios"}, indent=2))
    for s in summary.get("scenarios", []):
        print(f"{s['scenario']:<26} n={s['n']:<3} monitor {s['monitor_detected']}/{s['n']} med={s['monitor_ms_median']} ms | "
              f"poll {s['poll_detected']}/{s['n']} med={s['poll_ms_median']} ms | ofctl cmd med={s['ofctl_cmd_ms_median']} ms")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
