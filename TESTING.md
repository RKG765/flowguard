# Testing

Strategy: tests ship with every feature (unit + integration in the phase that adds it); Phase 9 is the systematic pass; every bug fix ships with a regression test. Long-running and root-only suites are separate targets.

| Target | Scope | State |
|---|---|---|
| `make test` | unit + Hypothesis property tests (`tests/unit`) under the core venv (3.10) and the engine venv (3.9, plus `tests/engine` with real Ryu and ZeroMQ) | exists |
| `make test-live` | `tests/integration`: real OVS + Mininet + the real engine process, attacked with `ovs-ofctl` (root) | exists (Phase 1) |
| `make docs-check` | generated docs are current and obey the evidence rules | exists |
| `make spike` | Phase 0 feasibility measurements (root, Mininet) | exists |
| `make test-e2e` | Playwright UI flows | planned (Phase 4) |
| `make test-security` | static analysis, dependency audit, authz/fuzz, helper allowlist | planned (Phase 7/9) |
| `make test-soak` | multi-hour soak | planned (Phase 9) |

Run: `make test` uses both venvs. `sudo make test-live` needs root, a running OVS and a free port 6653 (`flowguard doctor` first); each run builds a throw-away data directory and key, so it never touches your real key or golden store. Output of the last full run: `results/phase1_tests.txt`.

What the live suite checks: forged / modified / deleted / shadowing / cookie-copied rules and a tamper-and-quick-revert are detected from the monitor event; policy edits and key rotation produce zero alerts; the engine refuses to start without a valid key; alert JSON never contains the key.

Every bug found while building Phase 1 has a regression test: spool torn line, cookie-keyed grace exemption, event publish exceptions, empty AUTO blocks in the docs tool.

Environments covered so far: WSL2 Ubuntu 22.04 only. Native Ubuntu: not yet.
