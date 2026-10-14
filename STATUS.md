# FlowGuard status
<!-- AUTO:header -->
Last updated: 2026-10-14 | Current phase: 2, Core service, API, storage, auth | Overall: 3 of 12 phases done
Verified on: WSL2 Ubuntu 22.04: 2026-10-14 | Native Ubuntu 22.04: not yet
<!-- /AUTO:header -->

## Phase progress
<!-- AUTO:phase_table -->
| # | Phase | Status | Started | Finished |
|---|---|---|---|---|
| 0 | Environment doctor and feasibility spike | done | 2026-10-14 | 2026-10-14 |
| 1 | Engine L1 (signer, store, verifier, responder) | done | 2026-10-14 | 2026-10-14 |
| 2 | Core service, API, storage, auth | done | 2026-10-14 | 2026-10-14 |
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
  P2["2: Core service, API, storage, auth"]:::done
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
| Engine to core channel: ZeroMQ + durable spool + ordered acknowledgement | implemented | `make test (ZeroMQ + spool + ack unit tests); make test-live (engine to core, core restart)` | 2026-10-14 | WSL2 |
| Core service (FastAPI, SQLite WAL + Alembic, REST, WebSocket) | implemented | `make test (tests/api); make test-live (tests/integration/test_core_live.py); uvicorn smoke test` | 2026-10-14 | WSL2 |
| Auth (argon2id, sessions, roles, CSRF, lockout) + hash-chained audit log | implemented | `make test (role matrix over every route, CSRF, lockout, expiry, audit chain tamper test)` | 2026-10-14 | WSL2 |
| Privileged helper (allowlist) | planned | - | - | - |
| Attacks A1-A7 (A7 SIMULATED) | planned | - | - | - |
| Design system + app shell | planned | - | - | - |
| Dashboard pages + Attack Lab | planned | - | - | - |
| L2 data-plane prober | planned | - | - | - |
| L3 ML scorer worker | planned | - | - | - |
| Risk engine + policy | planned | - | - | - |
| Reports (summary + CSV now; PDF later) | partial | `make test (summary from stored alerts, CSV with formula-injection guard). PDF and evaluation results: Phase 6/8` | 2026-10-14 | WSL2 |
| flowguard CLI (start, stop, status, export) and make targets | planned | - | - | - |
| Ryu engine app (signed installs, monitor supervisor, passes, alerts) | implemented | `make test-live` | 2026-10-14 | WSL2 |
| Policy file + live policy reload (signed churn) | implemented | `make test; make test-live (policy edit = zero alerts)` | 2026-10-14 | WSL2 |
| HMAC key file checks, flowguard keygen, key rotation | implemented | `make test; bin/flowguard keygen; make test-live (rotation)` | 2026-10-14 | WSL2 |
| Session recorder (record + download; replay planned Phase 6) | partial | `make test (tests/api/test_ingest.py::test_recording_*)` | 2026-10-14 | WSL2 |
| Engine rule snapshots + status events for the core | implemented | `make test (build_snapshot); make test-live (rules reach the core)` | 2026-10-14 | WSL2 |
<!-- /AUTO:component_table -->

## What works (verified)
Each item names the command that proved it on WSL2 Ubuntu 22.04 on 2026-10-14. Test output: `results/phase2_tests.txt` (Phase 1: `results/phase1_tests.txt`).
- **Environment doctor:** `bin/flowguard doctor` as root passes every check (`docs/spike_evidence/doctor.txt`); run as a normal user it explains that OVS and Mininet need root.
- **Datapaths and lab:** kernel and userspace OVS datapaths work; `topo/topo_basic.py` runs 4 hosts on 1 switch (2-switch variant verified standalone) (`docs/spike_findings.md`).
- **Signed rules (L1):** canonical form, HMAC-in-cookie bound to dpid and epoch, rotation with a grace window, key-file checks (`make test`).
- **Live L1 detection and repair** (`make test-live`, `tests/integration/test_l1_live.py`): forged, modified, deleted, shadowing and cookie-copied rules plus tamper-and-quick-revert are detected from the monitor event and repaired or removed; policy edits and key rotation raise zero alerts.
- **Core service** (`make test`, `tests/api`): REST + WebSocket API on 127.0.0.1, SQLite WAL with Alembic migrations (checked against the models), argon2id auth with viewer/analyst/admin roles enforced on every route (role-matrix test), CSRF for cookie sessions, login lockout, session expiry and revocation, hash-chained audit log with tamper detection, versioned policy store, recordings, summary report and CSV export.
- **Engine to core, live** (`make test-live`, `tests/integration/test_core_live.py`): a real attack reaches the core's REST API and WebSocket with the engine's restore confirmation; rule integrity (per-rule status) and switch status are visible through the API; the core acknowledges the engine's spool; an alert raised while the core is down is stored after the core restarts; policy churn creates no alerts; key rotation requested through the API is carried out by the engine.
- **Real server:** `make run-core` (uvicorn) starts, binds 127.0.0.1 only, serves `/docs`, refuses anonymous API reads.

## What is simulated
Nothing yet. (The lying switch, attack A7, will be a SIMULATED wrapper in Phase 5 and badged as such.) All attacks so far are real `ovs-ofctl` commands against the lab switch.

## Test and review status
- `make test`: unit + property tests in both venvs and the core API tests; `make test-live`: L1 and engine-to-core live tests. Counts and exit codes: `results/phase2_tests.txt`.
- Not covered yet: engine restart / reconnect storms, monitor drop and recovery live, several switches, rate-limit behaviour live, load and soak, browser access from Windows (no UI yet), tamper timing races (Phase 9).
- QA / UX / security reviews: not started (Phases 9-10). Open findings: none recorded because no review has run.
- Environments: WSL2 only. Native Ubuntu not verified.

## Known issues and workarounds
- `api.launchpad.net` unreachable from this machine: PPAs are added manually in `setup_ubuntu.sh` (ADR-010).
- OVS 2.17.12 here does not support the OF1.4 flow monitor nor NXST over OF1.3; L1 uses an OF1.0 monitor session (ADR-004). Other OVS builds are untested.
- A tamper applied AND reverted inside the grace window of the engine's own change to the same slot is judged only after the window (ADR-011); probability not measured yet.
- Detect latency includes a 15 ms event debounce (`verify_debounce_ms`), by design.
- The policy document in the core is stored but **not enforced** (`enforced: false`) until the Phase 5 risk engine (ADR-016).
- The core's login lockout is in memory and resets on restart (ADR-014). The audit chain detects in-place edits, not a full rewrite by someone with database write access (ADR-015).
- In the live tests the core runs as root next to Mininet; separate OS users for engine and core arrive in Phase 7. The core writes the engine's `<spool>.ack`, so both need access to the data directory (ADR-013).
- Windows reaches WSL as user `rkg`; the repo is in `/home/rkg/flowguard` (ADR-001). Editing a file from Windows tools removes its exec bit.
- GitHub: `main` is pushed over HTTPS (login via `gh`; token stored in plain text in `~/.config/gh/hosts.yml`, see `HANDOFF.md`).
- `setup_ubuntu.sh` was verified by re-running on an already provisioned WSL2, not on a pristine machine.

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
1. Owner reviews the Phase 2 summary and says "continue".
2. Phase 3: produce the screen designs from the UI brief; give the owner the Google Stitch brief text (Claude has no Stitch access).
3. Design system: tokens (dark-first, light theme), glass and dense-data surfaces, typography, motion with reduced-motion/transparency fallbacks, contrast checks on glass.
4. App shell: sidebar, top bar with live status (WebSocket), Ctrl+K command palette, theme toggle, toasts; login and first-run screens against the real API.
5. `/design` living style guide; Playwright smoke test and contrast checks.

## Open questions for the owner
- None blocking. Phase 3 will ask whether you want to use Google Stitch for the screen designs.
