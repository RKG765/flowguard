# Phase 0 spike findings

Date: 2026-10-14. Machine: Windows 11 + WSL2, `Ubuntu-22.04`, kernel `6.6.87.2-microsoft-standard-WSL2`, Open vSwitch 2.17.12, Mininet 2.3.0, Ryu 4.34 (Python 3.9), root user. **One machine, one environment**: everything below is unverified on native Ubuntu.
Reproduce: `make spike` (root, about 10 minutes). Raw evidence for every claim is in `docs/spike_evidence/`; tables are produced by `scripts/spike/summarize.py` from `s3_*.json`.

## Summary of answers
| Question | Answer | Evidence |
|---|---|---|
| Does the OVS kernel datapath work on WSL2? | **Yes** on this kernel: the `openvswitch` module loads and a bridge uses `system@ovs-system`. | `s1_datapath.txt` |
| Does the userspace datapath (`netdev`) work as a fallback? | **Yes**: bridge uses `netdev@ovs-netdev`; Mininet pingall and the full monitor test pass on it. | `s1_datapath.txt`, `s2_mininet.txt`, `s3_ofctl_monitor_userspace.json` |
| Does Mininet work, with explicit dpids? | **Yes**: `mn --test pingall` 0% dropped on both datapaths; `topo_basic.py` standalone and with the controller; two-switch variant standalone pingall 0% loss. `tc` shaping works (`sch_htb`, `sch_netem` loaded). | `s2_mininet.txt`, `s2_two_switch_standalone.txt` |
| Does a Ryu learning switch work with the agreed table layout (ACL in table 0, learning in table 1)? | **Yes**, on OF1.3 and OF1.4: pingall 0% loss and `dump-flows` shows tables 0 and 1. | `s3_*.json` (`pingall_loss_percent`, `tables_in_dump`), `s3_*_dump_flows.txt` |
| Does `OFPFlowStatsRequest(table_id=0)` return only table 0? | **Yes**, `poll_tables_seen=[0]`; median round trip 1.0 to 1.4 ms across the four runs. | `s3_*.json` (`poll_tables_seen`, `poll_rtt_ms_median`) |
| Does OF1.4 `OFPMP_FLOW_MONITOR` work against this OVS? | **No.** OVS logs `NXST_FLOW_MONITOR has bad flags 0xffff` and replies with an error: this OVS decodes the standard monitor request as the Nicira one. 0 events in every scenario. | `s3_of14.json`, `ovs-vswitchd.log` line quoted in `DECISIONS.md` ADR-004 |
| Does Nicira `NXST_FLOW_MONITOR` work over OpenFlow 1.3 (as an experimenter multipart)? | **No.** OVS answers `OFPBRC_BAD_SUBTYPE` to the Ryu experimenter message. 0 events. OVS's own `ovs-ofctl -O OpenFlow13 monitor` (and `-O OpenFlow14`) also fails with `OFPBRC_BAD_VERSION`. | `s3_nxst13.json`, `s4_ovs_monitor_cli.txt` (the `ovs-vswitchd.log` excerpt at its end also shows the `bad flags 0xffff` and `BAD_SUBTYPE` lines) |
| Does `NXST_FLOW_MONITOR` work over an **OpenFlow 1.0** session on a passive port? | **Yes.** Events (ADDED / MODIFIED / DELETED with table and cookie) arrive for changes made through OF1.3 `ovs-ofctl` commands. Priority is not printed in the text format. | `s3_ofctl_monitor.json`, `s4_ovs_monitor_cli.txt` |

## Detection latency: monitor vs polling table 0 every 0.5 s
Each trial is a real `ovs-ofctl` change against switch `s1`; `t0` is taken before the `ovs-ofctl` process is started, so **both latencies include the process start (median command duration about 21 to 24 ms)**. The monitor figures are therefore an upper bound and mostly measure `ovs-ofctl` startup.

Kernel datapath, NXST over OF1.0 (`docs/spike_evidence/s3_ofctl_monitor.json`):

| scenario | n | monitor detected | monitor median ms | poll(0.5 s) detected | poll median ms |
|---|---|---|---|---|---|
| modify_acl | 30 | 30/30 | 21.6 | 30/30 | 261.7 |
| revert_acl | 30 | 30/30 | 21.9 | 30/30 | 273.8 |
| add_forged | 30 | 30/30 | 21.1 | 30/30 | 272.0 |
| delete_forged | 1 | 1/1 | 21.3 | 1/1 | 291.0 |
| delete_acl | 1 | 1/1 | 25.6 | 1/1 | 156.6 |
| restore_acl | 1 | 1/1 | 17.6 | 1/1 | 19.3 |
| **tamper_and_quick_revert** | 30 | **30/30** | 21.1 | **0/30** | - |

Userspace datapath (`s3_ofctl_monitor_userspace.json`): same picture, monitor 10/10 on modify, revert, forged add and quick revert; polling 0/10 on quick revert.

`tamper_and_quick_revert` is two `ovs-ofctl mod-flows` commands back to back (about 40 ms total). Polling saw none of the 30 (kernel) and none of the 10 (userspace); the monitor saw all of them. This is a small sample of one tamper pattern: it shows polling can miss fast reverts, it does not give a detection probability versus interval (that is measured in Phase 9). The delete/restore rows have n=1 and are only a smoke check.

## Decision: L1 mode = event-driven (ADR-004)
Monitor session over OpenFlow 1.0 on a passive port, used as a trigger; a targeted `OFPFlowStatsRequest(table_id)` over the OF1.3 controller connection is the ground truth; a slow reconciliation poll is the safety net. Because a fast revert leaves the table equal to the golden rules by the time the stats arrive, the verifier must also raise `unattributed_change` for critical-table events not explained by its own FlowMods (this is a design requirement for Phase 1, not yet built or tested).

## Things that broke or surprised us (and what we did)
| Problem | Fix / decision |
|---|---|
| `add-apt-repository ppa:deadsnakes/ppa` timed out: `api.launchpad.net` is unreachable here, while the PPA mirror and keyserver respond (`setup_run1.log`) | Add the PPA by hand with a fingerprint-checked key (ADR-010) |
| `ryu` exposes no `__version__`; the first doctor reported a false FAIL | Doctor reads versions from package metadata (regression covered by the doctor run on the venv check) |
| `wsl.exe -- bash -c '...$VAR...'` expands variables before the inner shell runs | Put commands in script files (documented in `CLAUDE.md`) |
| `ovs-vsctl -f csv` triple-quotes strings, so a "controller connected" check always returned False in the first spike runs | Parser fixed in `topo/topo_basic.py`; the final evidence runs report `controller_connected=true` |
| `ovs-ofctl monitor` prints no priority | The spike matches events by table and match text; the engine will verify via stats anyway |

## Versions that worked together
Python 3.9.25 (deadsnakes), `pip==23.3.2`, `setuptools==58.0.0`, `ryu==4.34`, `eventlet==0.30.2`, `dnspython==1.16.0`, `pyzmq==26.2.0`; full set in `requirements/engine.lock.txt`. `os-ken` was not needed and stays a documented fallback (ADR-003).

## Not tested in Phase 0
Native Ubuntu; OVS builds other than 2.17.12; two switches *with* a controller and monitor ports; the monitor session surviving a switch reconnect; monitor behavior under a high rule-change rate (events may be paused: `NXST` PAUSED/RESUMED); OVS version differences for the NX monitor text format.
