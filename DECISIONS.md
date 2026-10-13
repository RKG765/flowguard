# Architecture decisions

Format: context, decision, alternatives, consequences. Status is `accepted` unless noted. Evidence files are in `docs/spike_evidence/`.

## ADR-001: Repo lives on the WSL ext4 filesystem
- **Context:** The development machine is Windows 11 + WSL2; the product needs `chmod 0600` key files, fast `npm install`, and SQLite WAL.
- **Decision:** Repo at `/root/flowguard` (the only WSL user is root). Windows access via `\\wsl.localhost\Ubuntu-22.04\root\flowguard`. `D:\sds` holds the plan and a pointer file only. The owner will add a GitHub remote and clone on the native Ubuntu laptop.
- **Alternatives:** `/mnt/d/sds` (slow, no real permissions, unreliable SQLite WAL).
- **Consequences:** Development as root in WSL; the privilege-separated services (non-root core, root helper) are still built as specified and tested in Phases 2/7 with a dedicated service user.

## ADR-002: Separate processes; ZeroMQ between engine and core
- **Context:** Ryu runs on eventlet, FastAPI on asyncio; the Ryu loop must never block.
- **Decision:** Separate processes. Engine -> core over ZeroMQ PUSH/PULL on a Unix socket. In Ryu, events go into a bounded in-memory queue drained by one green thread using `zmq.green`; on overflow events are dropped and counted (`events_dropped_total`, a health metric). The web server never runs as root; the privileged helper is its own small process with a command allowlist.
- **Alternatives:** local HTTP + queue (heavier, more failure modes), shared SQLite (couples the two loops).
- **Consequences:** `pyzmq` in the engine venv (pinned, installed and import-checked by `flowguard doctor`). Status: `planned` for Phase 1/2; only the dependency is verified so far.

## ADR-003: Ryu 4.34 on Python 3.9 with pinned build tooling; os-ken is the fallback
- **Context:** Ryu 4.34 does not install/run cleanly on current tooling.
- **Decision:** `.venv-engine` on Python 3.9 (deadsnakes) with `pip==23.3.2`, `setuptools==58.0.0`, `ryu==4.34`, `eventlet==0.30.2`, `dnspython==1.16.0`, `pyzmq==26.2.0`. Full resolved set: `requirements/engine.lock.txt`. Verified: `ryu-manager --version` -> 4.34, and the spike controller runs and controls OVS (`docs/spike_evidence/`).
- **Fallback (not used):** `os-ken` (the maintained fork of Ryu used by OpenStack) if Ryu 4.34 breaks on a future toolchain. API is nearly identical (`os_ken` namespace). Switching would be recorded as a new ADR.
- **Consequences:** Python 3.9 comes from a PPA, so the setup script must add it (ADR-010).

## ADR-004: L1 detection is event-driven via an OpenFlow 1.0 Nicira monitor session, confirmed by a targeted stats request
- **Context:** Spike results (`docs/spike_findings.md`): OVS 2.17.12 rejects the standard OF1.4 `OFPMP_FLOW_MONITOR` and rejects `NXST_FLOW_MONITOR` over OpenFlow 1.3 (`OFPBRC_BAD_SUBTYPE`). `NXST_FLOW_MONITOR` works over an OpenFlow 1.0 session. Polling table 0 at 0.5 s missed every tamper-and-revert done within one `ovs-ofctl` pair; the monitor saw all of them.
- **Decision:** Mode = **event-driven**. Each lab switch exposes a passive OpenFlow port (`ptcp:6634+`). The engine runs a monitor session (`ovs-ofctl monitor tcp:127.0.0.1:<port> watch:` supervised as a subprocess in Phase 1) as a *trigger*. A trigger for a critical table causes a targeted `OFPFlowStatsRequest(table_id=...)` over the controller's OF1.3 connection, which is the ground truth the verifier checks against signed rules. A slow reconciliation poll (configurable, default 5 s) remains as a safety net for monitor drops.
- **Alternatives:** polling only (simpler, misses fast revert); OF1.4 monitor (not supported by this OVS); a native Python NXST client (more code; revisit if text parsing proves fragile).
- **Consequences:** If the attacker reverts before the confirming stats request, the table already matches the golden rules, so state comparison alone says "ok". The verifier therefore also raises `unattributed_change` for any critical-table event not explained by the engine's own FlowMods (tracked via the pending set). The monitor text format is parsed (events ADDED/DELETED/MODIFIED with table and cookie; priority is not printed). Limitation to document: events do not carry instructions, hence the confirm step. Whether the same holds on the native Ubuntu laptop's OVS build is `unverified` until re-run there.

## ADR-005: HMAC input binds dpid and epoch; short rotation window
- **Decision:** `tag = first 48 bits of HMAC-SHA256(K_epoch, canonical_bytes)` where `canonical_bytes` covers (dpid, epoch16, table_id, priority, normalized match, normalized instructions) and excludes counters, durations, timeouts, flags and the cookie. `cookie = (tag << 16) | epoch16`. `K_epoch = HMAC-SHA256(master_key, "flowguard-epoch" || epoch16)` so old epochs can be re-derived. After rotation the previous epoch is accepted for `rotation_grace_seconds` (config, default 300) and then rejected. dpids are explicit in the Mininet topology (`s1=0000000000000001`, `s2=0000000000000002`).
- **Why dpid:** otherwise a valid cookie could be reused on the same rule on a different switch.
- **Consequences:** 48-bit tag: forgery needs 2^47 expected online guesses against a verifier that restores on first sight; the realistic attack is copying/replaying, which the binding addresses. Status `planned` (Phase 1).

## ADR-006: Table layout
- **Decision:** Table 0 = security/ACL rules (miss -> `goto_table:1`). Table 1 = learning-switch rules (miss -> controller). `critical_tables` defaults to `[0]`. Verified in the spike: pingall 0% loss with this pipeline on OF1.3 and OF1.4.
- **Consequences:** Tampering with table 1 is out of L1 scope by default (configurable).

## ADR-007: OVS datapath
- **Decision:** `auto`: use the kernel datapath when `/sys/module/openvswitch` exists (or `modprobe` succeeds), otherwise the userspace datapath (`datapath_type=netdev`). On this WSL2 kernel (6.6.87.2) the kernel module loads and both datapaths work (`docs/spike_evidence/s1_datapath.txt`), so no custom kernel is needed.
- **Consequences:** The userspace path is exercised by `make spike` so the fallback is known to work when a machine lacks the module.

## ADR-008: Everything Python runs in a venv
- **Decision:** `.venv-engine` (3.9) for Ryu; `.venv-core` (3.10, `--system-site-packages`, because apt installs Mininet's module system-wide) for the lab, helper, core and tests. `bin/flowguard` and `scripts/doctor.py` use only the standard library so they work before venvs exist.

## ADR-009: Alert spool (no silent alert loss)
- **Decision:** Every alert is appended to `data/spool/alerts.jsonl` (fsync) before it is sent over ZeroMQ; the core acknowledges by sequence number. Unacknowledged records are replayed on reconnect. Rotation at 10 MiB per file, keep 5 files (50 MiB cap). When the cap is reached the oldest file is dropped, `spool_dropped_total` is incremented and a synthetic `spool_overflow` alert is emitted. All three numbers are in `config.example.yaml`. Status `planned` (Phase 1).

## ADR-010: Deadsnakes PPA is added manually
- **Context:** `add-apt-repository` needs `api.launchpad.net`, which timed out from this machine (`docs/spike_evidence/setup_run1.log`), while the PPA mirror and keyserver are reachable.
- **Decision:** `setup_ubuntu.sh` fetches the signing key from `keyserver.ubuntu.com`, checks its fingerprint (`F23C5A6C...5776`), and writes a `signed-by` source entry itself.
