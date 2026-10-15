# FlowGuard: run and show (Ubuntu 22.04, Phases 0-4)

Needs: a laptop booted into **Ubuntu 22.04** (other versions are not supported by the setup script),
internet for the first install, about 5 GB free disk, and a user with `sudo`.

## 0. Fresh laptop (once)
```bash
sudo apt update && sudo apt install -y git curl
```

## 1. Install (once, ~10-15 min)
```bash
git clone https://github.com/RKG765/flowguard.git && cd flowguard
sudo bash scripts/setup_ubuntu.sh
sudo bin/flowguard doctor          # every line should say PASS
```

## 2. Dashboard build (once, pick one)
```bash
make build-web                     # uses Node 20 from the setup script
```
or the prebuilt one from the GitHub release `v0.4.0-demo` (no Node needed):
```bash
curl -fLO https://github.com/RKG765/flowguard/releases/download/v0.4.0-demo/flowguard-web-dist-v0.4.0-demo.tar.gz
tar xzf flowguard-web-dist-v0.4.0-demo.tar.gz -C web
```

## 3. Start
**For a presentation (recommended):** one guided command. It starts everything, creates the login
(`admin` / `flowguard-demo`), tells you at each step what to show and say, makes the same switch changes as
the Phase 1 live tests (altered, forged, missing), shows the detection and the repair, a zero-alert policy
change, and automatic repair. Press Enter to go to the next step; Ctrl+C stops everything.
```bash
sudo make present
```
**Free-running dashboard** (no guided steps):
```bash
sudo make demo                     # automatic repair
sudo make demo MODE=alert_only     # repairs need an admin click (shows the Repair button)
```
Wait for `FLOWGUARD-STACK-READY`, open **http://127.0.0.1:8787** in Firefox on the same laptop,
create the admin, sign in.
Stop with **Ctrl+C**. If a run was interrupted: `sudo mn -c`.

## 3b. Streamlit operator console (optional second dashboard)
Once (needs internet): `make ui-setup`. Then, while `make demo` or `make present` is running, in another terminal:
```bash
cd ~/flowguard && make ui
```
Open **http://127.0.0.1:8501**. No login screen: the console only listens on 127.0.0.1 and signs in to the local core
with the demo account (`admin` / `flowguard-demo`, created by `make present`; override with `FG_USER=... FG_PASSWORD=... make ui`). Pages: Overview, Rules (signed vs on-switch,
admin Repair), Live Detection, Alerts & Incidents, Topology, Policy, Reports (CSV), Audit log (hash-chain check),
Engine (key rotation), Users, L2/L3 (planned). Screenshots: `docs/img/streamlit-*.png`.

## 4. What to show
| Page | Show |
|---|---|
| Overview | engine connected, L1 active, L2/L3 planned, live feed |
| Rules | 3 signed rules **Verified**; click one: signed vs on-switch |
| Topology | engine, switch s1 (green), 4 learned hosts |
| Live Detection | change a table-0 rule of `s1` outside the controller (the same changes the Phase 1 tests make, `tests/integration/test_l1_live.py`); the detection appears within milliseconds with its timeline |
| Alerts | plain-language explanation, timeline, diff; acknowledge / assign / note |
| `/design` | design system, live contrast check, light/dark |

## 5. Proof (tests)
```bash
make test                          # unit, property, API, web
sudo make test-live                # 19 live tests on a real OVS + Mininet lab
```
Screenshots: `docs/img/`. Status and evidence: `STATUS.md`, `results/phase4_tests.txt`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `doctor` says Open vSwitch is not running | `sudo systemctl restart openvswitch-switch` |
| `Missing .venv-core` / `.venv-engine` | re-run `sudo bash scripts/setup_ubuntu.sh` |
| port 8787 busy, or a previous run is stuck | `sudo pkill -f "[r]yu-manager"; sudo mn -c`, then start again |
