# FlowGuard status
<!-- AUTO:header -->
Last updated: 2026-10-15 | Current phase: 4, Core pages + Live Detection (tag demo-v0; attack execution descoped) | Overall: 5 of 12 phases done
Verified on: WSL2 Ubuntu 22.04: 2026-10-15 | Native Ubuntu 22.04: not yet
<!-- /AUTO:header -->

## Phase progress
<!-- AUTO:phase_table -->
| # | Phase | Status | Started | Finished |
|---|---|---|---|---|
| 0 | Environment doctor and feasibility spike | done | 2026-10-14 | 2026-10-14 |
| 1 | Engine L1 (signer, store, verifier, responder) | done | 2026-10-14 | 2026-10-14 |
| 2 | Core service, API, storage, auth | done | 2026-10-14 | 2026-10-14 |
| 3 | Design system and dashboard shell | done | 2026-10-14 | 2026-10-14 |
| 4 | Core pages + Live Detection (tag demo-v0; attack execution descoped) | done | 2026-10-14 | 2026-10-15 |
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
  P3["3: Design system and dashboard shell"]:::done
  P4["4: Core pages + Live Detection (tag demo-v0; attack execution descoped)"]:::done
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
| Privileged attack-execution helper (descoped from Phase 4 by the owner; see ADR-019) | planned | - | - | - |
| Attack scripts A1-A7 (descoped from Phase 4 by the owner; see ADR-019) | planned | - | - | - |
| Design system (tokens, glass/data surfaces, components, /design style guide) | implemented | `make test-web (104 tests incl. contrast of every text token, both themes); make test-e2e (axe, reduced motion/transparency)` | 2026-10-14 | WSL2 |
| Dashboard: shell, setup, sign-in, Overview, Rules, Alerts/Incidents, Topology, Live Detection (Phase 5-6 pages pending) | partial | `make test-e2e; make test-e2e-live (live engine: rules, topology, detection, admin repair)` | 2026-10-15 | WSL2 |
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
| Google Stitch design system + screens (via Stitch MCP) | partial | `Stitch MCP: create_project, create/update_design_system, generate_screen_from_text (Overview render retrieved; list_screens returned no screens)` | 2026-10-14 | Stitch (cloud) |
| Live Detection page (observation mode) | implemented | `make test-e2e-live` | 2026-10-15 | WSL2 |
| Dashboard-requested repair (admin, audited; works in alert-only mode) | implemented | `make test (core API); make test-e2e-live (rule removed from the switch)` | 2026-10-15 | WSL2 |
<!-- /AUTO:component_table -->

## What works (verified)
Each item names the command that proved it on WSL2 Ubuntu 22.04. Test output: `results/phase4_tests.txt` (earlier: `results/phase1_tests.txt` .. `phase3_tests.txt`).
- **Environment doctor:** `sudo bin/flowguard doctor` passes every check.
- **Lab and L1 engine** (`make test-live`): forged, modified, deleted, shadowing and cookie-copied rules plus tamper-and-quick-revert are detected from the monitor event and repaired or removed; policy edits and key rotation raise zero alerts.
- **Core service** (`make test`, `make test-live`): REST + WebSocket on 127.0.0.1, migrations, argon2id auth with roles on every route, CSRF, lockout, hash-chained audit log, policy store (not enforced yet), recordings, reports; live ingest from the engine incl. after a core restart; admin-only, audited rule repair requests.
- **Dashboard** (`make test`, `make test-e2e`, `make test-e2e-live`):
  - first-run setup, sign-in with lockout countdown, shell with live engine status, Ctrl+K, themes, toasts, `/design` style guide;
  - **Rules:** every rule of every switch with its integrity status, filters and search, signed vs actual diff, admin repair with confirmation, CSV export;
  - **Alerts and Incidents:** plain-language "what happened / why / what FlowGuard did", measured timeline, diff, acknowledge, assign, notes, close and reopen;
  - **Topology:** engine, switches coloured by rule integrity, hosts the switch has learned;
  - **Live Detection** (observation mode): detections appear live with timings and the rule before repair; in alert-only mode an admin repairs from the dashboard and the rule disappears from the real switch (checked against OVS in the test);
  - reachable from the Windows browser at http://127.0.0.1:5173 when `make dev-web` runs in WSL (checked 2026-10-15);
  - accessibility: contrast unit tests for every token, axe with no serious/critical violation on every page shown (incl. live pages).

## What is simulated
Nothing. FlowGuard does not execute attacks (ADR-019). The Live Detection test makes one rule change on the throw-away lab switch, the same case as the Phase 1 integration tests.

## Test and review status
- `make test`, `make test-e2e`, `make test-e2e-live`, `make test-live`: counts and exit codes in `results/phase4_tests.txt`.
- Not covered yet: large rule tables in the browser (virtualization is unit-tested only), several switches live, tablet widths, load and soak, reconnect storms (Phase 9).
- QA / UX / security reviews: not started (Phases 9-10). Open findings: none recorded because no review has run.
- Environments: WSL2 only. Native Ubuntu not verified.

## Known issues and workarounds
- **Scope change (ADR-019):** the Attack Lab's attack execution (privileged helper, attack scripts, Run button, compare mode) is descoped; the page is Live Detection (observation). Phase 5 items framed as product-run attacks (A6, A7) need the owner's scope decision first.
- Inter-switch links are not discovered; multi-switch labs show switches without links (ADR-020).
- Stitch's `list_screens` returned no screens; only the Overview render was retrievable (ADR-017). The Stitch API key sits in plain text in `D:\sds\.mcp.json` (outside the repo) and was pasted in the chat; the owner plans to rotate it.
- OVS 2.17.12 here does not support the OF1.4 flow monitor nor NXST over OF1.3; L1 uses an OF1.0 monitor session (ADR-004).
- A tamper applied AND reverted inside the grace window of the engine's own change to the same slot is judged only after the window (ADR-011).
- The policy document is stored but **not enforced** (ADR-016). Login lockout is in memory (ADR-014). The audit chain detects in-place edits, not a full rewrite (ADR-015).
- Engine status (counters, hosts) reaches the core every 5 s, so those values can lag a detection by a few seconds; the Live Detection page shows their age.
- In the live tests the core runs as root next to Mininet; separate OS users arrive in Phase 7. The dashboard is served by the Vite dev server for now; the core serving `web/dist` is Phase 7.

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
1. Owner reviews the Phase 4 summary (screenshots in `docs/img/`, tag `demo-v0`) and decides the Phase 5 scope (ADR-019 note).
2. Phase 5 (defensive scope): L2 data-plane canary probes for critical rules with expected-vs-actual results.
3. L3: dataset from normal lab traffic and legitimate rule churn, Isolation Forest vs one-class SVM, scorer in its own process, model metadata in the UI.
4. Risk engine fusing L1/L2/L3 under the stored policy, dry run first; Probes and ML pages.
5. Tests and docs for all of it; tag `novelty-complete`.

## Open questions for the owner
- Phase 5 scope: confirm the defensive scope above (no product-run attack scenarios), or say what to change.
- Please rotate the Stitch API key (it was pasted in the chat) and put the new one in `D:\sds\.mcp.json`.
