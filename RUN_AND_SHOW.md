# FlowGuard: run and show (Ubuntu 22.04, prototype)

Needs: a laptop booted into **Ubuntu 22.04** (WSL2 works too), internet for the first install, about 5 GB free disk,
and a user with `sudo`.

## 1. Install (once, ~10-15 min)
```bash
sudo apt update && sudo apt install -y git curl
git clone https://github.com/RKG765/flowguard.git && cd flowguard
sudo bash scripts/setup_ubuntu.sh
sudo bin/flowguard doctor          # every line should say PASS
```

## 2. Start the whole prototype (one command)
```bash
sudo bin/flowguard start           # or: sudo make start        (MODE=alert_only to repair by admin click)
```
It builds the dashboard and the console environment the first time (uses `uv` when installed), then starts the Mininet
lab, the Ryu engine, the core, the website and the Streamlit console. The engine and the core run as their own unprivileged
accounts (`flowguard-engine`, `flowguard-core`, created by `scripts/service-users.sh`); only the lab itself is root. `FLOWGUARD_RUN_AS_ROOT=1`
keeps the old all-root behaviour.

| What | Address |
|---|---|
| Website (React, with the Demo Lab page) | http://127.0.0.1:8787 |
| Operator console (Streamlit, signs in by itself) | http://127.0.0.1:8501 |

Sign in to the website with the demo account `admin` / `flowguard-demo` (the console creates it the first time you open
it, so open the console first), or create your own admin on first visit.
Check it: `bin/flowguard status`. Stop it: **Ctrl+C**, or `sudo bin/flowguard stop`. After an interrupted run: `sudo mn -c`.
Logs are in `/tmp/flowguard-logs/`. Save the records of a run: `sudo bin/flowguard export` (no keys are copied).

Guided alternative for a presentation: `sudo make present` (a script tells you what to show and say at each step).

## 3. What to show (about 8 minutes)
| Page | Show |
|---|---|
| Overview | engine connected, the **patch panel** (one port per signed rule, all green), L1 and L2 **Active**, L3 **Waiting** until the first detection |
| Rules | click a rule: signed vs on-switch side by side, with the 8-band **tag stripe** of each (a changed rule breaks the stripe) |
| **Demo Lab** | pick a switch, run "Change a rule", "Add an unknown rule", "Delete a rule", "Hide a rule", "Change and revert": the switch turns red, the log shows detect time and signed vs found, then **Repair now**. This page is **simulated** and says so; nothing touches a switch |
| Live Detection / Alerts | change a table-0 rule of `s1` outside the controller (the same changes the Phase 1 tests make, `tests/integration/test_l1_live.py`); the detection appears within milliseconds with its timeline, its risk decision and its L3 score |
| Probes (L2) | canary probe results per rule; a rule that is listed but no longer acts as signed fails its probe |
| ML (L3) | the anomaly score and the reasons behind it |
| Policy | dry run, weights, thresholds and the action per severity. Turn dry run off and choose `quarantine_port`: a rule tied to a port gets that port cut, and the port is listed with a Release button. ML alone never repairs |
| Reports | numbers from stored alerts, **Report PDF** and CSV, and **recorded sessions**: an admin records, anyone with analyst rights replays the session in the browser at 1x to 100x (a recording, clearly marked, no lab needed) |
| Audit, Settings | the hash-chained audit log (tamper check), users and key rotation |

## 4. Proof
```bash
make test                          # unit, property, API, web
make test-security                 # authentication, roles, CSRF, validation, crypto
make test-e2e                      # real browser, accessibility check on every page in both themes
sudo make test-live                # live tests on a real Open vSwitch + Mininet lab
sudo make eval                     # measured detection and repair times -> docs/results.md
sudo make test-soak                # two minutes of normal operation: no false alerts, no failed probes
sudo bash scripts/pristine-check.sh # builds a clean Ubuntu 22.04 userland and runs the setup script and the non-lab tests in it
```
Numbers and what they do not show: `docs/results.md`. Status and evidence: `STATUS.md`, `QA_REPORT.md`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `doctor` says Open vSwitch is not running | `sudo systemctl restart openvswitch-switch` |
| `Missing .venv-core` / `.venv-engine` | re-run `sudo bash scripts/setup_ubuntu.sh` |
| the console says "Engine has not reported yet" | an old core may hold port 8787: `sudo bin/flowguard stop`, then `sudo bin/flowguard start` |
| port busy or a previous run is stuck | `sudo bin/flowguard stop; sudo mn -c`, then start again |
