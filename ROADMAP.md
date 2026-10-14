# Roadmap

Phase list and status live in `STATUS.md` (generated from `docs/graphs/status.json`). The agreed plan is `IMPLEMENTATION_PLAN.md` (copy kept in `D:\sds`).

## Milestone tags
- `demo-v0` after Phase 4 (Attack Lab with A1-A6).
- `novelty-complete` after Phase 5 (L2, L3, risk engine, lying switch).

## Done: Phase 0 (doctor + spike), Phase 1 (engine L1), Phase 2 (core service), Phase 3 (design system + shell)
See `STATUS.md`.

## Next: Phase 4 (Attack Lab and core pages, tag `demo-v0`)
Live Topology (React Flow), Rule Inspector (virtualized, golden vs observed diff, restore with confirmation), Alerts and Incidents (timeline, triage, plain-language explanations), Attack Lab (A1-A6 through the privileged helper with an allowlist, live split view, timing, before/after diff). Stitch screens for these pages first.

## Backlog and known gaps
- Core: persistent login limiter, external anchor for the audit chain head, separate OS users for engine/core with a shared group for the spool (Phase 7), replay of recorded sessions (Phase 6), PDF reports (Phase 6).
- Engine robustness to test in Phase 9: restart and reconnect storms, monitor drop/recovery live, runtime SQLite corruption, rate-limit behaviour live, many switches.
- Measure detection probability versus poll interval and the grace-window race (ADR-011).
- Engine process currently runs as the invoking user; privilege separation (non-root engine/core, root helper) arrives in Phases 2 and 4/7.
- Native Ubuntu verification of everything (OVS build may differ; monitor behavior must be re-measured).
- Decide whether to replace the `ovs-ofctl monitor` subprocess with a native NXST client if text parsing proves fragile.
- Closing the lab limitation (key and controller on the switch host) is out of scope; document only.
- Stitch brief for the dashboard (Phase 3).
- `make start|demo|eval|test-e2e|test-security|test-soak` and `flowguard start|stop|status|export`.
