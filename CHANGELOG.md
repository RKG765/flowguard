# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). One entry per phase or notable change.

## [Unreleased]

### Demo packaging (after `demo-v0`, release `v0.4.0-demo`)
- The core serves the built dashboard (`web/dist`) on its own port with client-route fallback, confined to the build directory (test added).
- `sudo make demo [MODE=alert_only]`: lab + engine + core + dashboard on http://127.0.0.1:8787 (`scripts/demo.sh`); `RUN_AND_SHOW.md`.
- GitHub release `v0.4.0-demo` with the prebuilt dashboard archive.
- Streamlit operator console (`ui/streamlit_app.py`, `make ui-setup` once, then `make ui` on http://127.0.0.1:8501): a second front end over the same core API, no attack execution (ADR-019). Checked on WSL2 2026-10-15: all 11 pages load without errors; a forged rule appeared on Live Detection and Rules and the Repair button removed it from the switch.
- `sudo make present`: guided presentation demo (`scripts/present.py`, ADR-021). Checked end to end on WSL2 2026-10-15: altered, forged and missing each detected (about 18 ms) and repaired from alert-only mode, a policy change gave 4/4 verified with 0 alerts, and restore mode repaired automatically.

### Phase 4: core pages and Live Detection (tag `demo-v0`)
#### Added
- Rule Inspector (virtualized table, status filters with counts, search, signed-vs-actual diff, admin repair with confirmation, CSV export), Alerts and Incidents (plain-language explanation, measured timeline, diff, acknowledge, assign, notes, close/reopen), Live Topology (React Flow: engine, switches by integrity status, learned hosts), Live Detection page in observation mode.
- Engine: `golden_instructions` in snapshots, learned hosts in the status, dashboard-requested repairs (works in alert-only mode). Core: `POST /api/rules/repair` (admin, audited).
- Tests: repair API test; web unit tests for formatting, virtualization and switch health; Playwright against a live lab + engine + core (`make test-e2e-live`); Windows browser access to the WSL dev server verified.
#### Changed
- The Attack Lab is the Live Detection page; attack execution from the product was descoped (ADR-019).
#### Fixed (found by tests)
- Rule table header row sat outside its table role (axe `aria-required-parent`).
- Topology over-zoomed with few nodes and hid hosts; React Flow painted its own background.
- The top bar showed "Waiting for engine status" for up to 5 s after a reload.

### Phase 3: design system and dashboard shell
#### Added
- Google Stitch (via MCP): project, "FlowGuard Glass" design system, generated Overview design (ADR-017).
- `web/`: React + TypeScript + Vite dashboard: tokens for dark/light themes, glass and data surfaces, reduced-motion and reduced-transparency modes, components (buttons, fields, banners, status/severity/mode badges, KPI cards, skeletons, empty states), app shell (sidebar, top bar with live engine status over WebSocket, Ctrl+K palette, theme toggle, toasts with click-through), first-run setup, sign-in with lockout countdown, Overview on real API data, honest "planned" pages, `/design` living style guide with live contrast measurements.
- Tests: 104 web unit tests (contrast of every token in both themes, API client CSRF, auth bootstrap, live feed), 8 Playwright end-to-end tests with axe accessibility scans and screenshots in `docs/img/`.
- `make test` now includes the web typecheck and unit tests; `make test-e2e`, `make dev-web`, `make build-web`.
#### Fixed (found by the new tests)
- Light-theme amber text 4.47:1 (below AA); white text on blue/red buttons 3.16/3.39:1; red/blue badge text on its tint 4.17/4.29:1.
- The pre-paint theme script was blocked by the page's own CSP; moved to a same-origin file.
- Loading skeletons were invisible in the light theme.

### Phase 2: core service, API, storage, auth
#### Added
- `core/`: FastAPI app factory, SQLite (WAL) with Alembic migrations, ZeroMQ receiver + ordered spool tail with acknowledgement, incident grouping, WebSocket hub with one-time tickets, argon2id auth with roles/CSRF/lockout, hash-chained audit log, policy store (not enforced yet), session recorder, report summary and CSV export, engine status and key-rotation request.
- Engine: per-table rule snapshots and periodic status on the channel.
- Tests: role matrix over every route, auth/CSRF/lockout/expiry, ingest and spool acknowledgement, real ZeroMQ receiver, WebSocket, audit tamper detection, CSV formula injection, migrations-vs-models; live engine-to-core tests including a core restart.
- `make run-core`; `make test` now includes the API tests.
#### Fixed
- Doctor reported a misleading OVS failure when run as a normal user; it now says what to do.

### Phase 1: engine L1 (signer, store, verifier, responder)
#### Added
- `engine/`: `canonical` (deterministic rule bytes), `crypto` (HMAC-in-cookie bound to dpid and epoch, rotation window, key-file checks), `store` (SQLite golden store), `verifier` (missing/altered/shadow/forged, attribution, grace), `responder` (restore/delete, rate limit, dry run), `spool` (durable alert spool with rotation), `channel` (non-blocking ZeroMQ), `monitor_parser`, `policy`, `config`, `ryu_codec`, `app` (the Ryu engine).
- `flowguard keygen`; `make test` (both venvs) and `make test-live`.
- Live integration tests: forged, modified, deleted, shadowing, cookie-copy and tamper-and-revert attacks; policy churn and key rotation with zero alerts; key hygiene.
#### Changed
- Repo moved to `/home/rkg/flowguard` (ADR-001); venvs rebuilt.
#### Fixed (found by tests)
- Alert spool lost the next record after a crash left a torn line.
- Grace-window exemption was keyed by cookie, so a copied golden cookie hid a forged rule (ADR-011).
- A delayed confirmation pass could hold back a live monitor event (earlier pass now supersedes).
- `EventChannel.publish` could raise on odd events.

### Phase 0: environment doctor and feasibility spike
#### Added
- Repo skeleton, living documentation set, `docs/graphs/status.json` and `scripts/update_docs.py` (`make docs`, `make docs-check`).
- `scripts/setup_ubuntu.sh`, `scripts/doctor.py` / `doctor.sh`, `bin/flowguard doctor`.
- `topo/topo_basic.py`: 1 switch + 4 hosts (optional 2nd switch), explicit dpids, datapath auto-selection.
- Feasibility spikes S1-S3 with raw evidence in `docs/spike_evidence/`; `docs/spike_findings.md`.
- Threat model with the lab limitation (controller, key and switch share one host).
#### Decided
- ADR-001..010 in `DECISIONS.md` (event-driven L1 via OF1.0 NXST monitor; dpid+epoch bound HMAC; table layout; alert spool limits).
