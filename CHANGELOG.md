# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). One entry per phase or notable change.

## [Unreleased]

### Phase 0: environment doctor and feasibility spike
#### Added
- Repo skeleton, living documentation set, `docs/graphs/status.json` and `scripts/update_docs.py` (`make docs`, `make docs-check`).
- `scripts/setup_ubuntu.sh`, `scripts/doctor.py` / `doctor.sh`, `bin/flowguard doctor`.
- `topo/topo_basic.py`: 1 switch + 4 hosts (optional 2nd switch), explicit dpids, datapath auto-selection.
- Feasibility spikes S1-S3 with raw evidence in `docs/spike_evidence/`; `docs/spike_findings.md`.
- Threat model with the lab limitation (controller, key and switch share one host).
#### Decided
- ADR-001..010 in `DECISIONS.md` (event-driven L1 via OF1.0 NXST monitor; dpid+epoch bound HMAC; table layout; alert spool limits).
