# Testing

Strategy: tests ship with every feature (unit + integration in the phase that adds it); Phase 9 is the systematic pass; every bug fix ships with a regression test. Long-running and root-only suites are separate targets.

| Target | Scope | State |
|---|---|---|
| `make test` | pytest unit tests (`tests/unit`) | exists: docs tooling and doctor only |
| `make docs-check` | generated docs are current and obey the evidence rules | exists |
| `make spike` | Phase 0 feasibility measurements (root, Mininet) | exists |
| `make test-e2e` | Playwright UI flows | planned (Phase 4) |
| `make test-security` | static analysis, dependency audit, authz/fuzz, helper allowlist | planned (Phase 7/9) |
| `make test-soak` | multi-hour soak | planned (Phase 9) |

Run: `make test` uses `.venv-core`. Integration tests that need Mininet require root and a running OVS (`flowguard doctor` first).

Environments covered so far: WSL2 Ubuntu 22.04 only. Native Ubuntu: not yet.
