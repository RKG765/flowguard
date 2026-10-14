# Handoff: how to resume

Read `CLAUDE.md`, `STATUS.md`, then this file. Last rewritten at the end of Phase 4 (2026-10-15).

## Where things are
- Repo: `/home/rkg/flowguard` in WSL distro `Ubuntu-22.04` (user `rkg`). From Windows: `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`. Pointer + approved plan also in `D:\sds`.
- Branch `main`, pushed to GitHub; tag `demo-v0` marks the end of Phase 4.
- Next phase: **5, L2 prober, L3 ML, risk engine (tag `novelty-complete`)**. The owner must say "continue" and confirm the Phase 5 scope first (ADR-019: FlowGuard does not execute attacks; the brief's A6/A7 were framed as product-run attacks).
- Design source: Google Stitch project `4222547732368189816`, design system `assets/4690579397531729796` (MCP server configured in `D:\sds\.mcp.json`, key there in plain text, never copy it into the repo).

## Open the project
```powershell
wsl -d Ubuntu-22.04 --cd ~/flowguard                    # as rkg (normal shell)
wsl -d Ubuntu-22.04 -u root --cd /home/rkg/flowguard    # as root, for Mininet/OVS tests
```

## GitHub
Remote `origin` = `https://github.com/RKG765/flowguard.git` via `gh` (device flow as `rkg`). Push with `git push --follow-tags` as `rkg`. If it asks for a username: `gh auth login --web`, enter the code at https://github.com/login/device.

## Run things by hand
```bash
cd ~/flowguard
bin/flowguard keygen                                   # once; key at ~/.config/flowguard/hmac.key (0600)
sudo .venv-core/bin/python topo/topo_basic.py --hold   # lab (root), controller 127.0.0.1:6653, monitor port 6634
PYTHONPATH=. .venv-engine/bin/ryu-manager --ofp-tcp-listen-port 6653 engine.app      # engine (FLOWGUARD_RESPONSE_MODE=alert_only to try dashboard repairs)
make run-core                                          # core API on http://127.0.0.1:8787 (docs at /docs)
make dev-web                                           # dashboard on http://127.0.0.1:5173 (open it from the Windows browser)
```
All share `data/` in the repo by default (`FLOWGUARD_DATA_DIR` moves it). A complete throw-away stack in one command (root): `sudo .venv-core/bin/python tests/e2e_live/stack.py --core-port 8787 --response-mode alert_only` (then `make dev-web` with the default proxy). After an interrupted run: `sudo mn -c; pkill -f ryu-manager`.

## Verify the environment
```bash
cd ~/flowguard
sudo bin/flowguard doctor   # expect no FAIL
make test                   # Python (both venvs) + core API + web typecheck/unit tests
make test-e2e               # Playwright against a throw-away core (no engine)
make docs-check
sudo make test-live         # live L1 + engine-to-core tests (root)
sudo make test-e2e-live     # Playwright against a live lab + engine + core (root; uses the invoking user's Playwright browsers)
```
As root without sudo (e.g. `wsl -u root`): `PW_BROWSERS=/home/rkg/.cache/ms-playwright make test-e2e-live`.

## Second laptop (native Ubuntu 22.04)
```bash
gh auth login && gh repo clone RKG765/flowguard ~/flowguard && cd ~/flowguard
sudo bash scripts/setup_ubuntu.sh && sudo bin/flowguard doctor
(cd web && npm ci && npx playwright install chromium) && sudo bash -c 'cd web && npx playwright install-deps chromium'
bin/flowguard keygen && make test && make test-e2e && sudo make test-live && sudo make test-e2e-live
```

## What to do next (Phase 5)
Confirm scope with the owner (STATUS.md "Open questions"). Hooks already in place: `core/models.py` has `probe_results` and `ml_scores` tables and `/api/probes`, `/api/ml/scores` return `available: false`; the policy document (`/api/policies`) has weights, thresholds and per-severity actions with `enforced: false`; nav entries `/probes` and `/ml` render the Planned page until built (`components/layout/nav.ts`, `built: true` switches them on).

## Gotchas learned
- Python only from the venvs; an unanswered "Create a default Unix user" prompt blocks every `wsl.exe` call; Windows reaches WSL as `rkg`; editing files from Windows drops exec bits.
- Mininet is root-only with fixed names: one lab at a time; a detached `nohup` job started through `wsl.exe` dies when that call returns.
- Playwright: fresh cookies per test (sign in through `page.request`); wait for the shell before shortcuts; set `colorScheme: "dark"`; the Playwright version here does not support `webServer.gracefulShutdown` (the make target cleans up the lab instead).
- Engine status (counters, hosts) is pushed every 5 s; the shell seeds it from `/api/engine/status` on load.
- React Flow: give `ReactFlow` a `key` that changes with the node count so `fitView` re-runs when hosts appear; cap `maxZoom` at 1.
- The page CSP forbids inline scripts (`public/theme-init.js`).
- No `Co-Authored-By` trailers in commits (owner instruction).
