# Roadmap

Phase list and status live in `STATUS.md` (generated from `docs/graphs/status.json`). The agreed plan is `IMPLEMENTATION_PLAN.md` (copy kept in `D:\sds`).

## Milestone tags
- `demo-v0` after Phase 4 (Attack Lab with A1-A6).
- `novelty-complete` after Phase 5 (L2, L3, risk engine, lying switch).

## Next: Phase 1 (engine L1)
`canonical`, `crypto` (dpid + epoch bound, rotation window), golden store, `install_signed_rule()`, verifier fed by the OF1.0 NXST monitor (ADR-004) with `unattributed_change`, responder, alert spool (ADR-009).

## Backlog and known gaps
- Native Ubuntu verification of everything (OVS build may differ; monitor behavior must be re-measured).
- Decide whether to replace the `ovs-ofctl monitor` subprocess with a native NXST client if text parsing proves fragile.
- Closing the lab limitation (key and controller on the switch host) is out of scope; document only.
- Stitch brief for the dashboard (Phase 3).
- `make start|demo|eval|test-e2e|test-security|test-soak` and `flowguard start|stop|status|export`.
