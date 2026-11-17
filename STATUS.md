# FlowGuard status
<!-- AUTO:header -->
Last updated: 2026-11-17 | Current phase: 11, Fix loop and release gate | Overall: 8 of 12 phases done
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
| 5 | L2 prober, L3 ML, risk engine, lying switch (tag novelty-complete) | done | 2026-11-16 | 2026-11-17 |
| 6 | Remaining pages, reports, polish | in_progress | 2026-11-16 | - |
| 7 | Packaging and hardening | in_progress | 2026-11-17 | - |
| 8 | Evaluation and docs | done | 2026-11-17 | 2026-11-17 |
| 9 | Rigorous testing (full QA pass) | in_progress | 2026-11-17 | - |
| 10 | Persona-based review | done | 2026-11-17 | 2026-11-17 |
| 11 | Fix loop and release gate | in_progress | 2026-11-17 | - |
<!-- /AUTO:phase_table -->

<!-- AUTO:progress_graph -->
```mermaid
flowchart LR
  P0["0: Environment doctor and feasibility spike"]:::done
  P1["1: Engine L1 (signer, store, verifier, responder)"]:::done
  P2["2: Core service, API, storage, auth"]:::done
  P3["3: Design system and dashboard shell"]:::done
  P4["4: Core pages + Live Detection (tag demo-v0; attack execution descoped)"]:::done
  P5["5: L2 prober, L3 ML, risk engine, lying switch (tag novelty-complete)"]:::done
  P6["6: Remaining pages, reports, polish"]:::in_progress
  P7["7: Packaging and hardening"]:::in_progress
  P8["8: Evaluation and docs"]:::done
  P9["9: Rigorous testing (full QA pass)"]:::in_progress
  P10["10: Persona-based review"]:::done
  P11["11: Fix loop and release gate"]:::in_progress
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
| Design system "Patch Panel" (tokens, panels, port strip, tag stripe, light and dark) | implemented | `make test-web (115 tests incl. contrast of every text token, both themes); make test-e2e (axe)` | 2026-11-17 | WSL2 |
| Dashboard: all pages (Overview, Topology, Rules, Alerts, Live Detection, Demo Lab, Probes, ML, Policy, Reports, Audit, Settings) | implemented | `make test-e2e (10 browser tests, axe on every page in both themes); live captures in .impeccable/review/` | 2026-11-17 | WSL2 |
| L2 canary prober (counter-based probes of signed rules) | implemented | `make test (unit); make test-live (tests/integration/test_l2_live.py: healthy pass, shadowing rule fails, ICMP/ARP/IPv6/in_port/masked rules probed)` | 2026-11-17 | WSL2 |
| L3 anomaly scorer (statistical baseline inside the engine, not a neural network) | implemented | `make test (tests/unit/test_phase5.py); make test-live (score and reasons reach the core API)` | 2026-11-17 | WSL2 |
| Risk engine, policy enforcement and port quarantine | implemented | `make test; make test-live (tests/integration/test_phase5_live.py: policy decides repair; quarantine cuts and releases a port)` | 2026-11-17 | WSL2 |
| Reports (summary + CSV now; PDF later) | partial | `make test (summary from stored alerts, CSV with formula-injection guard). PDF and evaluation results: Phase 6/8` | 2026-10-14 | WSL2 |
| Packaging: flowguard start/stop/status/export, one-command prototype (separate OS users and pristine-machine install still open) | partial | `bin/flowguard start (lab, engine, core, website and console up; status checked)` | 2026-11-17 | WSL2 |
| Ryu engine app (signed installs, monitor supervisor, passes, alerts) | implemented | `make test-live` | 2026-10-14 | WSL2 |
| Policy file + live policy reload (signed churn) | implemented | `make test; make test-live (policy edit = zero alerts)` | 2026-10-14 | WSL2 |
| HMAC key file checks, flowguard keygen, key rotation | implemented | `make test; bin/flowguard keygen; make test-live (rotation)` | 2026-10-14 | WSL2 |
| Session recorder (record + download; replay planned Phase 6) | partial | `make test (tests/api/test_ingest.py::test_recording_*)` | 2026-10-14 | WSL2 |
| Engine rule snapshots + status events for the core | implemented | `make test (build_snapshot); make test-live (rules reach the core)` | 2026-10-14 | WSL2 |
| Google Stitch design system + screens (via Stitch MCP) | partial | `Stitch MCP: create_project, create/update_design_system, generate_screen_from_text (Overview render retrieved; list_screens returned no screens)` | 2026-10-14 | Stitch (cloud) |
| Live Detection page (observation mode) | implemented | `make test-e2e-live` | 2026-10-15 | WSL2 |
| Dashboard-requested repair (admin, audited; works in alert-only mode) | implemented | `make test (core API); make test-e2e-live (rule removed from the switch)` | 2026-10-15 | WSL2 |
| Demo Lab (simulated four-switch topology; labelled Simulated; touches no switch) | implemented | `make test-e2e (simulate, detect, repair); make test-web (tamper/repair model)` | 2026-11-17 | WSL2 |
| Streamlit operator console (same palette; Demo Lab, quarantine release, L2/L3 pages) | partial | `compiled and exercised against the live stack; screenshots in .impeccable/review/console-*.png; no automated UI test` | 2026-11-17 | WSL2 |
| make eval, make test-soak, make test-security | implemented | `sudo make eval; sudo make test-soak; make test-security` | 2026-11-17 | WSL2 |
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
  - one-command demo: `sudo make demo` serves lab + engine + core + built dashboard on http://127.0.0.1:8787 (checked 2026-10-15: ready, 3/3 rules verified, switch and monitor up, 4 hosts learned); see `RUN_AND_SHOW.md`;
  - accessibility: contrast unit tests for every token, axe with no serious/critical violation on every page shown (incl. live pages).

## What is simulated
Only the **Demo Lab** pages (website and console): an in-memory four-switch model, labelled "Simulated", that touches no switch and no engine. Everything else shown comes from the engine. FlowGuard does not execute attacks (ADR-019); the live tests and `make eval` make rule changes on the throw-away lab switch with the lab's own tooling, the same cases as the Phase 1 integration tests.

## Test and review status
- Final run 2026-11-17 (`QA_REPORT.md`): core 218, engine 141, security 137, web 116, browser e2e 10 (axe on every page, both themes), live lab 26 passed; `sudo make eval` 40/40 detected, 0 false alerts (`docs/results.md`); soak pass.
- Not covered yet: large rule tables in the browser (virtualization is unit-tested only), several switches live, tablet widths, load, reconnect storms, native Ubuntu.
- AI-simulated security, code and design reviews done (`SECURITY_REVIEW.md`, `UX_REVIEW.md`); all high and medium findings fixed. No human testers. Open items: `RELEASE_CHECKLIST.md`.
- Environments: WSL2 only. Native Ubuntu not verified.

## Known issues and workarounds
- **Scope change (ADR-019):** the Attack Lab's attack execution (privileged helper, attack scripts, Run button, compare mode) is descoped; the page is Live Detection (observation). Phase 5 items framed as product-run attacks (A6, A7) need the owner's scope decision first.
- Inter-switch links are not discovered; multi-switch labs show switches without links (ADR-020).
- Stitch's `list_screens` returned no screens; only the Overview render was retrievable (ADR-017). The Stitch API key sits in plain text in `D:\sds\.mcp.json` (outside the repo) and was pasted in the chat; the owner plans to rotate it.
- OVS 2.17.12 here does not support the OF1.4 flow monitor nor NXST over OF1.3; L1 uses an OF1.0 monitor session (ADR-004).
- A tamper applied AND reverted inside the grace window of the engine's own change to the same slot is judged only after the window (ADR-011).
- The policy document is enforced for `dry_run`, `weights`, `thresholds` and `actions` (ADR-022); `response_mode` and `critical_tables` still come from the engine config. Login lockout is in memory (ADR-014). The audit chain detects in-place edits, not a full rewrite (ADR-015).
- Engine status (counters, hosts) reaches the core every 5 s, so those values can lag a detection by a few seconds; the Live Detection page shows their age.
- In the lab the engine and core run as root next to Mininet; separate OS users are not done. The core serves the built dashboard (`web/dist`) on :8787.

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
| Eval (live lab): tampering trials detected (forged, altered, missing, shadow; 10 each) | 40/40 trials | `results/eval.json` |
| Eval (live lab): false alerts over 10 legitimate policy install/retire cycles | 0 alerts | `results/eval.json` |
| Eval (live lab): altered rule, change to alert (wall clock, median) | 25.2 ms | `results/eval.json` |
| Eval (live lab): altered rule, engine detect latency (median) | 16.2 ms | `results/eval.json` |
| Eval (live lab): altered rule, time to restore (median) | 12.3 ms | `results/eval.json` |
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
