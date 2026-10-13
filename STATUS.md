# FlowGuard status
<!-- AUTO:header -->
Last updated: 2026-10-14 | Current phase: 0, Environment doctor and feasibility spike | Overall: 1 of 12 phases done
Verified on: WSL2 Ubuntu 22.04: 2026-10-14 | Native Ubuntu 22.04: not yet
<!-- /AUTO:header -->

## Phase progress
<!-- AUTO:phase_table -->
| # | Phase | Status | Started | Finished |
|---|---|---|---|---|
| 0 | Environment doctor and feasibility spike | done | 2026-10-14 | 2026-10-14 |
| 1 | Engine L1 (signer, store, verifier, responder) | not_started | - | - |
| 2 | Core service, API, storage, auth | not_started | - | - |
| 3 | Design system and dashboard shell | not_started | - | - |
| 4 | Attack Lab and core pages (tag demo-v0) | not_started | - | - |
| 5 | L2 prober, L3 ML, risk engine, lying switch (tag novelty-complete) | not_started | - | - |
| 6 | Remaining pages, reports, polish | not_started | - | - |
| 7 | Packaging and hardening | not_started | - | - |
| 8 | Evaluation and docs | not_started | - | - |
| 9 | Rigorous testing (full QA pass) | not_started | - | - |
| 10 | Persona-based review | not_started | - | - |
| 11 | Fix loop and release gate | not_started | - | - |
<!-- /AUTO:phase_table -->

<!-- AUTO:progress_graph -->
```mermaid
flowchart LR
  P0["0: Environment doctor and feasibility spike"]:::done
  P1["1: Engine L1 (signer, store, verifier, responder)"]:::not_started
  P2["2: Core service, API, storage, auth"]:::not_started
  P3["3: Design system and dashboard shell"]:::not_started
  P4["4: Attack Lab and core pages (tag demo-v0)"]:::not_started
  P5["5: L2 prober, L3 ML, risk engine, lying switch (tag novelty-complete)"]:::not_started
  P6["6: Remaining pages, reports, polish"]:::not_started
  P7["7: Packaging and hardening"]:::not_started
  P8["8: Evaluation and docs"]:::not_started
  P9["9: Rigorous testing (full QA pass)"]:::not_started
  P10["10: Persona-based review"]:::not_started
  P11["11: Fix loop and release gate"]:::not_started
  P0 --> P1
  P1 --> P2
  P2 --> P3
  P3 --> P4
  P4 --> P5
  P5 --> P6
  P6 --> P7
  P7 --> P8
  P8 --> P9
  P9 --> P10
  P10 --> P11
  classDef done fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;
  classDef in_progress fill:#b7791f,stroke:#5c3b0d,color:#ffffff;
  classDef not_started fill:#4a5568,stroke:#1a202c,color:#ffffff;
  classDef blocked fill:#c53030,stroke:#63171b,color:#ffffff;
  classDef implemented fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;
  classDef partial fill:#b7791f,stroke:#5c3b0d,color:#ffffff;
  classDef planned fill:#4a5568,stroke:#1a202c,color:#ffffff;
```
<!-- /AUTO:progress_graph -->

## Component status
<!-- AUTO:component_table -->
| Component | Status | Verified by | Date | Environment |
|---|---|---|---|---|
| Living docs + status tooling (update_docs.py) | implemented | `make docs-check && make test` | 2026-10-14 | WSL2 |
| Environment doctor + flowguard CLI (doctor only) | implemented | `bin/flowguard doctor` | 2026-10-14 | WSL2 |
| scripts/setup_ubuntu.sh | partial | `bash scripts/setup_ubuntu.sh (re-run on a partly provisioned WSL2; pristine-machine install not yet tested)` | 2026-10-14 | WSL2 |
| Mininet lab topology (4 hosts, 1 or 2 switches, explicit dpids) | implemented | `scripts/spike/run_all.sh (standalone pingall, controller-attached run, two-switch standalone pingall)` | 2026-10-14 | WSL2 |
| Phase 0 spike harness (make spike) | implemented | `scripts/spike/run_all.sh S1-S3 + doctor; s4_ovs_monitor_cli.sh and the two-switch pingall run individually afterwards` | 2026-10-14 | WSL2 |
| Canonical form + HMAC cookie (dpid, epoch bound) | planned | - | - | - |
| Golden store + install_signed_rule | planned | - | - | - |
| L1 verifier + NXST monitor session | planned | - | - | - |
| Responder (restore, rate limit) | planned | - | - | - |
| ZeroMQ event channel + alert spool | planned | - | - | - |
| Core service (FastAPI, SQLite, WebSocket) | planned | - | - | - |
| Auth, roles, audit log | planned | - | - | - |
| Privileged helper (allowlist) | planned | - | - | - |
| Attacks A1-A7 (A7 SIMULATED) | planned | - | - | - |
| Design system + app shell | planned | - | - | - |
| Dashboard pages + Attack Lab | planned | - | - | - |
| L2 data-plane prober | planned | - | - | - |
| L3 ML scorer worker | planned | - | - | - |
| Risk engine + policy | planned | - | - | - |
| Reports (PDF/CSV) | planned | - | - | - |
| flowguard CLI (start, stop, status, export) and make targets | planned | - | - | - |
<!-- /AUTO:component_table -->

## What works (verified)
Each item names the command that proved it on WSL2 Ubuntu 22.04 on 2026-10-14.
- **Environment doctor:** `bin/flowguard doctor` -> 14 PASS, 0 WARN, 0 FAIL (`docs/spike_evidence/doctor.txt`). Includes a real Mininet ping test.
- **OVS datapaths:** kernel module loads on this WSL2 kernel and the userspace datapath also works (`docs/spike_evidence/s1_datapath.txt`).
- **Mininet lab:** `topo/topo_basic.py` pingall 0% loss standalone, attached to Ryu, and in the two-switch standalone variant (`s2_mininet.txt`, `s2_two_switch_standalone.txt`, `s3_*.json`).
- **Ryu 4.34 on Python 3.9** controls OVS with the agreed table layout (ACL table 0, learning switch table 1) on OF1.3 and OF1.4 (`s3_*.json`).
- **Event-driven change detection is feasible:** an OpenFlow 1.0 Nicira flow-monitor session sees every tamper, including fast tamper-and-revert, where polling does not (`docs/spike_findings.md`, numbers below).
- **Docs tooling:** `make docs-check` and `make test` (unit tests for `update_docs.py`, doctor, CLI).

## What is simulated
Nothing yet. (The lying switch, attack A7, will be a SIMULATED wrapper in Phase 5 and badged as such.)

## Test and review status
- Unit tests: `make test` covers docs tooling, doctor and CLI only. There is no product code to test yet.
- Integration: the Phase 0 spikes (`make spike`) are measurements, not pass/fail test suites.
- QA / UX / security reviews: not started (Phases 9-10). Open findings: none recorded because no review has run.
- Environments: WSL2 only. Native Ubuntu not verified.

## Known issues and workarounds
- `api.launchpad.net` unreachable from this machine: PPAs are added manually in `setup_ubuntu.sh` (ADR-010).
- OVS 2.17.12 here does not support the OF1.4 flow monitor nor NXST over OF1.3; the L1 design uses an OF1.0 monitor session (ADR-004).
- `wsl.exe -- bash -c '...$VAR...'` expands `$VAR` too early; use script files (see `CLAUDE.md`).
- `setup_ubuntu.sh` was verified by re-running on an already partly provisioned WSL2, not on a pristine machine.
- The optional second switch has only been verified standalone (no controller, no monitor ports).

## Measured numbers so far
<!-- AUTO:metrics -->
| Metric | Value | Source |
|---|---|---|
| Spike: monitor (NXST over OF1.0) detections, tamper-and-quick-revert, kernel datapath | 30/30 trials | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: polling table 0 every 0.5 s detections, same scenario | 0/30 trials | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: monitor median latency, modify of an ACL rule (includes ovs-ofctl start-up, upper bound) | 21.6 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: polling (0.5 s) median latency, same scenario | 261.7 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: targeted table-0 stats request round trip, median | 1.12 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
<!-- /AUTO:metrics -->
These are Phase 0 spike measurements on one machine, not evaluation results.

## Next 5 steps
1. Owner reviews the Phase 0 summary and says "continue".
2. Phase 1: `canonical.py` and `crypto.py` (dpid + epoch bound, rotation window) with unit and property tests.
3. Golden store + `install_signed_rule()`.
4. Verifier fed by the OF1.0 NXST monitor, with `unattributed_change` and the pending-set grace window.
5. Responder (restore, rate limit) + alert spool, then a Mininet integration test.

## Open questions for the owner
- None blocking. Optional: add the GitHub remote when ready (`HANDOFF.md` has the commands).
