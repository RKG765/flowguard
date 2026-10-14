# Testing

Strategy: tests ship with every feature (unit + integration in the phase that adds it); Phase 9 is the systematic pass; every bug fix ships with a regression test. Long-running and root-only suites are separate targets.

| Target | Scope | State |
|---|---|---|
| `make test` | unit + Hypothesis property tests (`tests/unit`) under the core venv (3.10) and the engine venv (3.9, plus `tests/engine` with real Ryu and ZeroMQ), and the core API tests (`tests/api`) | exists |
| `make test-live` | `tests/integration`: real OVS + Mininet + the real engine process, attacked with `ovs-ofctl`, plus the core service fed live by the engine (root) | exists (Phases 1-2) |
| `make docs-check` | generated docs are current and obey the evidence rules | exists |
| `make spike` | Phase 0 feasibility measurements (root, Mininet) | exists |
| `make test-e2e` | Playwright in Chromium against a throw-away core: setup, sign-in, lockout, palette, theme, reduced motion/transparency, keyboard, axe on every page shown | exists (Phase 3) |
| `make test-web` | web typecheck + Vitest unit tests (also run by `make test`) | exists (Phase 3) |
| `make test-e2e-live` | Playwright against a throw-away lab + engine (alert-only) + core (`tests/e2e_live/stack.py`): rules and topology from the live engine, a live detection with its explanation, an admin repair that removes the rule from the switch, audit entry (root) | exists (Phase 4) |
| `make test-security` | static analysis, dependency audit, authz/fuzz, helper allowlist | planned (Phase 7/9) |
| `make test-soak` | multi-hour soak | planned (Phase 9) |

Run: `make test` uses both venvs. `sudo make test-live` needs root, a running OVS and a free port 6653 (`flowguard doctor` first); each run builds a throw-away data directory and key, so it never touches your real key or golden store. Output of the last full run: `results/phase2_tests.txt` (Phase 1: `results/phase1_tests.txt`).

What the live suite checks: forged / modified / deleted / shadowing / cookie-copied rules and a tamper-and-quick-revert are detected from the monitor event; policy edits and key rotation produce zero alerts; the engine refuses to start without a valid key; alert JSON never contains the key.

Every bug found while building Phase 1 has a regression test: spool torn line, cookie-keyed grace exemption, event publish exceptions, empty AUTO blocks in the docs tool.

Environments covered so far: WSL2 Ubuntu 22.04 only. Native Ubuntu: not yet.

## Core API tests (`tests/api`, Phase 2)
- `test_roles.py`: every route is classified; unauthenticated -> 401; every role against every route; every 403 is in the audit log; a viewer cannot escalate.
- `test_auth.py`: first-run setup once, password policy, uniform login errors, lockout, logout revocation, CSRF for cookie sessions (Bearer exempt), session expiry, disabling/password change kills sessions, last-admin guard.
- `test_ingest.py`: idempotent alerts/updates/snapshots, incident grouping, ordered spool tail with acknowledgement, resume after restart, half-written lines, rotated files, real ZeroMQ receiver, recordings, path-safe recording names.
- `test_admin_features.py`: policy validation/versioning, reports from stored data only, CSV formula-injection guard, audit chain tamper detection, control-character stripping, key-rotation control file, health, WebSocket tickets and streaming, migrations match models.

## Live core tests (`tests/integration/test_core_live.py`)
Rule integrity and switch status reach the core; an attack reaches the WebSocket and REST with its restore confirmation and the spool is acknowledged; an alert raised while the core is down is stored after restart; policy churn is silent; key rotation requested through the API is carried out by the engine.

## Dashboard tests (`web/`, Phase 3)
- `src/styles/contrast.test.ts`: WCAG AA for every text token on bg, surface, surface-2, glass and its own badge tint, in both themes; white text on filled buttons. Reads `tokens.css` directly.
- `src/lib/lib.test.ts`: API client sends the CSRF token on changes only and maps errors (incl. Retry-After); auth bootstrap decides setup / sign-in / restored session / offline; live feed wording, 50-item cap, unseen count, refetch triggers.
- `src/components/ui/ui.test.tsx`: every rule-status and severity badge has an icon and a text label; field labels/hints/errors are wired with aria; KPI cards show an honest empty text.
- `e2e/shell.spec.ts` (Playwright, serial, fresh core in `/tmp/fg-e2e`): see the table above; screenshots land in `docs/img/`. Needs Chromium: `cd web && npx playwright install chromium` (system libraries: `sudo npx playwright install-deps chromium`).
