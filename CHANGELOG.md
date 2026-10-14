# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). One entry per phase or notable change.

## [Unreleased]

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
