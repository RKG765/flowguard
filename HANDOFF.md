# Handoff: how to resume

Read `CLAUDE.md`, `STATUS.md`, then this file. Last rewritten at the end of Phase 3 (2026-10-14).

## Where things are
- Repo: `/home/rkg/flowguard` in WSL distro `Ubuntu-22.04` (user `rkg`). From Windows: `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`. Pointer + approved plan also in `D:\sds`.
- Branch `main`, pushed to GitHub (see "GitHub"). `git log --oneline` lists the phase commits.
- Next phase: **4, Attack Lab and core pages (tag `demo-v0` at the end)**. The owner must say "continue" first.
- Design source: Google Stitch project `4222547732368189816` ("FlowGuard - SDN flow-rule integrity dashboard"), design system `assets/4690579397531729796` ("FlowGuard Glass"). The Stitch MCP server is configured in `D:\sds\.mcp.json` (key in plain text there, outside the repo; never copy it into the repo). Tools: `mcp__stitch__*` (generate_screen_from_text can time out while still succeeding: do not retry, poll `get_project`; `list_screens` returned nothing in Phase 3, the project thumbnail was the only retrievable render).

## Open the project
```powershell
wsl -d Ubuntu-22.04 --cd ~/flowguard                    # as rkg (normal shell)
wsl -d Ubuntu-22.04 -u root --cd /home/rkg/flowguard    # as root, for Mininet/OVS tests
```

## GitHub
Remote `origin` = `https://github.com/RKG765/flowguard.git` (HTTPS) via `gh auth login` (device flow, done 2026-10-14 as `rkg`; token in plain text in `~/.config/gh/hosts.yml`). Push with `git push` as `rkg`. If it asks for a username: `gh auth login --web` and enter the code at https://github.com/login/device.

## Run things by hand
There is no `flowguard start` yet (Phase 7).
```bash
cd ~/flowguard
bin/flowguard keygen                                   # once; key at ~/.config/flowguard/hmac.key (0600)
sudo .venv-core/bin/python topo/topo_basic.py --hold   # lab (root), controller 127.0.0.1:6653, monitor port 6634
PYTHONPATH=. .venv-engine/bin/ryu-manager --ofp-tcp-listen-port 6653 engine.app      # engine
make run-core                                          # core API on http://127.0.0.1:8787 (docs at /docs)
make dev-web                                           # dashboard on http://127.0.0.1:5173 (proxies /api to the core)
```
All share `data/` in the repo by default (`FLOWGUARD_DATA_DIR` moves it). The first visit to the dashboard opens the first-run admin setup. Open http://127.0.0.1:5173 from the Windows browser (WSL forwards localhost; not yet verified from Windows - check this early in Phase 4). After an interrupted run: `sudo mn -c; pkill -f ryu-manager`.

## Verify the environment
```bash
cd ~/flowguard
sudo bin/flowguard doctor   # expect no FAIL
make test                   # Python (both venvs) + core API + web typecheck/unit tests, ~90 s
make test-e2e               # Playwright (Chromium) against a throw-away core, ~30 s
make docs-check
sudo make test-live         # live L1 + engine-to-core tests (root; ~50 s)
```
First time on a machine: `cd web && npm ci && npx playwright install chromium` and `sudo npx playwright install-deps chromium`.

## Second laptop (native Ubuntu 22.04)
```bash
gh auth login && gh repo clone RKG765/flowguard ~/flowguard && cd ~/flowguard
sudo bash scripts/setup_ubuntu.sh && sudo bin/flowguard doctor
(cd web && npm ci && npx playwright install chromium) && sudo bash -c 'cd web && npx playwright install-deps chromium'
bin/flowguard keygen && make test && make test-e2e && sudo make test-live
```
Unverified there: kernel datapath, OVS version differences in `ovs-ofctl monitor ... watch:!initial` output, Python 3.9 from the PPA.

## What to do next (Phase 4)
`STATUS.md` "Next 5 steps". Building blocks already in `web/src`: `components/ui/primitives.tsx` (GlassCard, DataSurface, Button, Field, Banner, Badge, RuleStatusBadge, SeverityBadge, ModeBadge, Skeleton, EmptyState), `components/ui/Kpi.tsx`, `lib/api.ts` (typed client, CSRF), `lib/auth.ts` (`hasRole`), `lib/live.ts` (WebSocket store; `onInvalidate` refetches TanStack queries keyed `rules` / `alerts`), `components/layout/nav.ts` (routes with their phase; pages with `phase > 3` render `Planned`). Rule statuses and the core endpoints are listed in `ARCHITECTURE.md`. Keep the contrast policy (ADR-017): new colours go through `tokens.css` and the contrast test.

## Gotchas learned
- Python only from the venvs: `.venv-engine/bin/...` (Ryu, 3.9) and `.venv-core/bin/python` (core, lab, tests).
- An unanswered "Create a default Unix user" prompt in any WSL terminal blocks every `wsl.exe` call.
- Windows reaches WSL as the default user (`rkg`); `/root` is not readable from Windows.
- Editing a file with Windows tools drops its exec bit (`bin/flowguard`, `scripts/*.sh`, `scripts/doctor.py`): `chmod +x` again.
- Mininet is root-only and has fixed names: one lab at a time. A detached `nohup` job started through `wsl.exe` dies when that call returns.
- Test helper modules need unique names (`tests/api/apihelpers.py`).
- Playwright: each test gets fresh cookies (sign in through `page.request` first); wait for the shell to render before pressing shortcuts; headless Chromium reports a light OS theme unless `colorScheme: "dark"` is set.
- The page CSP forbids inline scripts (`public/theme-init.js` exists for that reason).
- `config.yaml`, keys, `.scratch/`, runtime `data/*` and `web/node_modules|dist|test-results` are gitignored.
- No `Co-Authored-By` trailers in commits (owner instruction).
