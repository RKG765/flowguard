#!/usr/bin/env python3
"""Print markdown tables from docs/spike_evidence/s3_*.json (the source of every number in spike_findings.md)."""
import json
from pathlib import Path

EV = Path(__file__).resolve().parents[2] / "docs" / "spike_evidence"
RUNS = [("of14", "OF1.4 OFPMP_FLOW_MONITOR"), ("nxst13", "NXST over OF1.3"),
        ("ofctl_monitor", "NXST over OF1.0 (kernel datapath)"), ("ofctl_monitor_userspace", "NXST over OF1.0 (userspace datapath)")]


def fmt(v):
    return "-" if v is None else f"{v:.1f}"


for key, title in RUNS:
    f = EV / f"s3_{key}.json"
    if not f.exists():
        print(f"\n### {title}: missing {f.name}")
        continue
    d = json.loads(f.read_text())
    topo = d.get("topology", {})
    print(f"\n### {title}  (file: `docs/spike_evidence/{f.name}`)")
    print(f"datapath={topo.get('datapath')}  controller_connected={d.get('controller_connected')}  "
          f"pingall_loss={d.get('pingall_loss_percent')}%  tables_in_dump={d.get('tables_in_dump')}  "
          f"poll_tables_seen={d.get('poll_tables_seen')}  poll_rtt_median_ms={d.get('poll_rtt_ms_median')}  "
          f"error={d.get('error')}")
    print("\n| scenario | n | monitor detected | monitor median ms | poll(0.5 s) detected | poll median ms |")
    print("|---|---|---|---|---|---|")
    for s in d.get("scenarios", []):
        print(f"| {s['scenario']} | {s['n']} | {s['monitor_detected']}/{s['n']} | {fmt(s['monitor_ms_median'])} | "
              f"{s['poll_detected']}/{s['n']} | {fmt(s['poll_ms_median'])} |")
    if d.get("scenarios"):
        print(f"\nofctl command duration median: {fmt(d['scenarios'][0]['ofctl_cmd_ms_median'])} ms (included in the latencies above)")
