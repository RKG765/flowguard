# FlowGuard: run and show (Ubuntu 22.04, Phases 0-4)

## 1. Install (once, needs internet, ~10 min)
```bash
git clone https://github.com/RKG765/flowguard.git && cd flowguard
sudo bash scripts/setup_ubuntu.sh
sudo bin/flowguard doctor          # every line should say PASS
```

## 2. Dashboard build (once, pick one)
```bash
make build-web                     # uses Node 20 from the setup script
```
or the prebuilt one from the GitHub release `v0.4.0-demo`:
```bash
gh release download v0.4.0-demo -R RKG765/flowguard -p 'flowguard-web-dist-*.tar.gz'
tar xzf flowguard-web-dist-*.tar.gz -C web
```

## 3. Start
```bash
sudo make demo                     # automatic repair
sudo make demo MODE=alert_only     # repairs need an admin click (shows the Repair button)
```
Wait for `FLOWGUARD-STACK-READY`, open **http://127.0.0.1:8787**, create the admin, sign in.
Stop with **Ctrl+C**. If a run was interrupted: `sudo mn -c`.

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
