# FlowGuard status
<!-- AUTO:header -->
Last updated: 2026-10-14 | Current phase: 1, Engine L1 (signer, store, verifier, responder) | Overall: 2 of 12 phases done
Verified on: WSL2 Ubuntu 22.04: 2026-10-14 | Native Ubuntu 22.04: not yet
<!-- /AUTO:header -->

## Phase progress
<!-- AUTO:phase_table -->
| # | Phase | Status | Started | Finished |
|---|---|---|---|---|
| 0 | Environment doctor and feasibility spike | done | 2026-10-14 | 2026-10-14 |
| 1 | Engine L1 (signer, store, verifier, responder) | done | 2026-10-14 | 2026-10-14 |
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
  P1["1: Engine L1 (signer, store, verifier, responder)"]:::done
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
| Canonical form + HMAC cookie (dpid, epoch bound) | implemented | `make test (unit + Hypothesis property tests, both venvs); make test-live (rotation)` | 2026-10-14 | WSL2 |
| Golden store + install_signed_rule | implemented | `make test; make test-live` | 2026-10-14 | WSL2 |
| L1 verifier + NXST monitor session + attribution | implemented | `make test; make test-live (forged, altered, missing, shadow, unattributed_change)` | 2026-10-14 | WSL2 |
| Responder (restore, rate limit) | implemented | `make test; make test-live (restore, removal, zero alerts on churn)` | 2026-10-14 | WSL2 |
| ZeroMQ event channel + durable alert spool | partial | `make test (real ZeroMQ + spool unit tests); make test-live (alerts spooled). Core-side receiver and acknowledgements are not built` | 2026-10-14 | WSL2 |
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
| Ryu engine app (signed installs, monitor supervisor, passes, alerts) | implemented | `make test-live` | 2026-10-14 | WSL2 |
| Policy file + live policy reload (signed churn) | implemented | `make test; make test-live (policy edit = zero alerts)` | 2026-10-14 | WSL2 |
| HMAC key file checks, flowguard keygen, key rotation | implemented | `make test; bin/flowguard keygen; make test-live (rotation)` | 2026-10-14 | WSL2 |
<!-- /AUTO:component_table -->

## What works (verified)
Each item names the command that proved it on WSL2 Ubuntu 22.04 on 2026-10-14. Test output: `results/phase1_tests.txt`.
- **Environment doctor:** `bin/flowguard doctor` (all checks PASS, `docs/spike_evidence/doctor.txt`), including a real Mininet ping test.
- **Datapaths and lab:** kernel and userspace OVS datapaths work; `topo/topo_basic.py` runs 4 hosts on 1 switch (2-switch variant verified standalone) (`docs/spike_findings.md`).
- **Signed rules (L1 core):** canonical form, HMAC-in-cookie bound to dpid and epoch, key rotation with a grace window, key-file checks (`make test`: unit and Hypothesis property tests under Python 3.9 and 3.10).
- **Live detection and repair against real OVS** (`make test-live`, 14 tests): a forged rule, a modified rule, a deleted rule, a shadowing rule, a cookie copied from a valid rule, and a tamper-and-quick-revert are all detected from the monitor event (not from the poll) and, except the revert, repaired or removed. A signed policy edit and a key rotation raise **zero** alerts. The engine refuses to start without a valid key.
- **Event-driven detection** over an OpenFlow 1.0 Nicira monitor session confirmed by a targeted table-0 stats request (ADR-004; `docs/spike_findings.md`).
- **Alert pipeline, engine side:** durable fsynced spool with rotation and a size cap, non-blocking ZeroMQ channel with counted drops (`make test`).
- **Docs tooling:** `make docs-check`.

## What is simulated
Nothing yet. (The lying switch, attack A7, will be a SIMULATED wrapper in Phase 5 and badged as such.) All attacks so far are real `ovs-ofctl` commands against the lab switch.

## Test and review status
- Unit + property tests: `make test` (core venv and engine venv), output in `results/phase1_tests.txt`.
- Live integration: `make test-live`, 14 tests, same file.
- Not covered yet: rate-limit behaviour live, engine restart / switch reconnect storms, SQLite corruption at runtime, several switches, monitor drop and recovery live, `alert_only` mode live, tamper timing races (Phase 9).
- QA / UX / security reviews: not started (Phases 9-10). Open findings: none recorded because no review has run.
- Environments: WSL2 only. Native Ubuntu not verified.

## Known issues and workarounds
- `api.launchpad.net` unreachable from this machine: PPAs are added manually in `setup_ubuntu.sh` (ADR-010).
- OVS 2.17.12 here does not support the OF1.4 flow monitor nor NXST over OF1.3; the L1 design uses an OF1.0 monitor session (ADR-004). Other OVS builds are untested.
- The engine reads rules by table over the OF1.3 connection; a tamper that is applied AND reverted inside the grace window of the engine's own change to the same slot is judged only after the window (ADR-011); its probability is not measured yet.
- Detect latency includes a 15 ms event debounce (`verify_debounce_ms`), by design.
- Windows reaches WSL as user `rkg`; the repo is in `/home/rkg/flowguard` (ADR-001). Editing a file from Windows tools removes its exec bit.
- GitHub push is not done: needs the owner to add the SSH public key to GitHub (see `HANDOFF.md`).
- `setup_ubuntu.sh` was verified by re-running on an already partly provisioned WSL2, not on a pristine machine.

## Measured numbers so far
<!-- AUTO:metrics -->
| Metric | Value | Source |
|---|---|---|
| Spike: monitor (NXST over OF1.0) detections, tamper-and-quick-revert, kernel datapath | 30/30 trials | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: polling table 0 every 0.5 s detections, same scenario | 0/30 trials | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: monitor median latency, modify of an ACL rule (includes ovs-ofctl start-up, upper bound) | 21.6 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: polling (0.5 s) median latency, same scenario | 261.7 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Spike: targeted table-0 stats request round trip, median | 1.12 ms | `docs/spike_evidence/s3_ofctl_monitor.json` |
| Phase 1 live, one run: altered rule, engine detect latency (monitor event to classified; includes the 15 ms debounce) | 18.07 ms | `results/phase1_live_alert_timings.json` |
| Phase 1 live, one run: altered rule, classified to restore sent | 0.36 ms | `results/phase1_live_alert_timings.json` |
| Phase 1 live, one run: altered rule, classified to switch confirmation event | 10.2 ms | `results/phase1_live_alert_timings.json` |
<!-- /AUTO:metrics -->
Phase 0 rows are spike measurements. Phase 1 rows are a single live run (one sample per attack), not an evaluation; the evaluation is Phase 8.

## Next 5 steps
1. Owner reviews the Phase 1 summary, adds the SSH key to GitHub, and says "continue".
2. Phase 2: core service skeleton (FastAPI, Alembic, SQLite), ZeroMQ receiver and alert acknowledgements (closes the spool loop).
3. REST resources, WebSocket stream, argon2 auth with roles, audit log.
4. OpenAPI docs and API tests including the role matrix.
5. Engine-to-core ingest verified with the live engine.

## Open questions for the owner
- Add the printed SSH public key to GitHub so the repo can be pushed (HANDOFF.md).
