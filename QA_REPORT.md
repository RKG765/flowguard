# QA report (prototype, 2026-11-17)

Environment: WSL2 Ubuntu 22.04, one Open vSwitch switch, Mininet, Python 3.10 (core) and 3.9 (engine), Node 20, Chromium via
Playwright. Everything here was run on this machine on the final code; nothing is copied from an earlier phase.

## Suites run
| Command | Result | What it covers |
|---|---|---|
| `make test` parts: core venv `pytest tests/unit tests/api` | **218 passed** | crypto, canonical form, store/spool/policy, risk engine, L3 baseline, L2 planning and judging, auth, roles on every route, CSRF, lockout, audit chain, admin features, ingest, quarantine API |
| engine venv `pytest tests/unit tests/engine` (Python 3.9) | **141 passed** | the pure engine modules under the Ryu interpreter |
| `make test-security` | **137 passed** | authentication, roles, CSRF, validation, crypto, canonical form, Phase 5 logic |
| `make test-web` (typecheck + vitest) | **116 passed** | components, contrast of every text token in both themes, formatting, tag stripe, Demo Lab model |
| `make test-e2e` (Playwright, Chromium) | **10 passed** | first run, sign in/out and lockout, palette, themes, Demo Lab simulate-detect-repair, **axe (WCAG 2 A/AA) on all 12 pages in dark and light**, reduced motion |
| `sudo make test-live` (real OVS + Mininet + engine + core) | **26 passed** (90 s) | forged, altered, deleted, shadowing rules and tamper-and-revert detected and repaired; policy churn and key rotation without alerts; engine to core delivery incl. a core restart; L2 probes (healthy pass, shadowing rule fails, ICMP/ARP/IPv6/in-port/masked rules probed with no false alarm); risk decision and L3 score on alerts; **a policy saved in the core changes whether the engine repairs**; **port quarantine cuts a host port and an admin release restores it** |
| `sudo make eval` | 40/40 trials detected, 0 false alerts | see `docs/results.md` |
| `sudo make test-soak` | **PASS** (60 s on the final code: 9 policy-churn cycles, no false alerts, no failed pings, 19 probe cycles with none failing, engine memory flat at 51.7 MB) | normal operation |

Also run by hand: `sudo bin/flowguard start` (whole prototype up; `status` checked), console and website opened against the live
engine with two real rule changes on the lab switch (screenshots in `.impeccable/review/`).

## Coverage
Line and branch coverage were **not measured**. The risky branches of the new code are covered by behaviour tests listed above
and by the live tests; the engine's Ryu glue (`engine/app.py`) is covered only by the live tests, not by unit tests.

## Issues found in this QA pass
| ID | Severity | Finding | Status |
|---|---|---|---|
| Q1 | high | Old unit test expected `bin/flowguard start` to be "not implemented"; it now ran the real command (blocked on a sudo prompt) | fixed: test rewritten to run only the read-only `status` |
| Q2 | high | `prototype.sh` logs vanished (the stack launcher recreates its data directory), so the script never saw "ready" | fixed: logs and pids live outside the data dir, under a root-owned `/run/flowguard` |
| Q3 | high | A stale core from an earlier session held port 8787 and hid the new stack's data | fixed: the launcher and `stop` clear any old core |
| Q4 | medium | Role matrix test failed: two new routes were not classified | fixed: added (viewer lists, admin releases) |
| Q5 | medium | e2e tests encoded the old design (blur, animated background, "planned" pages) | fixed and extended (Demo Lab, every page in both themes) |
| Q6 | medium | Narrow screens: the 224 px rail did not collapse | fixed: compact scrolling nav; tables and the topology scroll sideways |
| Q7 | various | Findings of the AI security, code and design reviews | see `SECURITY_REVIEW.md` and `UX_REVIEW.md` |

## Not tested (open)
Reconnect storms and engine restarts under load, runtime SQLite corruption, rate-limit behaviour live, **more than one switch
live**, large rule tables in the browser, load, real hardware, **native Ubuntu**, a pristine-machine install from
`setup_ubuntu.sh`, tablet widths, screen readers beyond axe. The Streamlit console has no automated UI test.
