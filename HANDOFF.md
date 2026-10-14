# Handoff: how to resume

Read `CLAUDE.md`, `STATUS.md`, then this file. Last rewritten at the end of Phase 2 (2026-10-14).

## Where things are
- Repo: `/home/rkg/flowguard` in WSL distro `Ubuntu-22.04` (user `rkg`). From Windows: `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`. Pointer + approved plan also in `D:\sds`.
- Branch `main`, pushed to GitHub (see "GitHub"). `git log --oneline` lists the phase commits.
- Next phase: **3, design system and dashboard shell**. The owner must say "continue" first.

## Open the project
```powershell
wsl -d Ubuntu-22.04 --cd ~/flowguard                    # as rkg (normal shell)
wsl -d Ubuntu-22.04 -u root --cd /home/rkg/flowguard    # as root, for Mininet/OVS tests
```

## GitHub
Remote `origin` = `https://github.com/RKG765/flowguard.git` (HTTPS). Authentication is `gh auth login` (browser device flow, done once on 2026-10-14 as user `rkg`; `gh auth setup-git` makes git use it). The token is stored in plain text in `~/.config/gh/hosts.yml` (mode 0600): revoke it at https://github.com/settings/applications if the machine is shared. Push with `cd ~/flowguard && git push` (as `rkg`, not root). If `git push` asks for a username, run `gh auth login --web` and enter the code at https://github.com/login/device.
New machine (native Ubuntu): install `gh` from the official apt repo, `gh auth login`, `gh repo clone RKG765/flowguard ~/flowguard`.

## Run things by hand
There is no `flowguard start` yet (Phase 7).
```bash
cd ~/flowguard
bin/flowguard keygen                                   # once; key at ~/.config/flowguard/hmac.key (0600)
sudo .venv-core/bin/python topo/topo_basic.py --hold   # lab (root), controller 127.0.0.1:6653, monitor port 6634
PYTHONPATH=. .venv-engine/bin/ryu-manager --ofp-tcp-listen-port 6653 engine.app      # engine
make run-core                                          # core API on http://127.0.0.1:8787 (docs at /docs)
```
All three share `data/` in the repo by default (`FLOWGUARD_DATA_DIR` moves it). First use of the core: `POST /api/setup {"username","password"}` creates the admin (only while no user exists), then `POST /api/auth/login`. The core reads the engine's spool and writes `<spool>.ack`, so run engine and core as the same user (or root) until Phase 7 separates them. After an interrupted run: `sudo mn -c; pkill -f ryu-manager`.

## Verify the environment
```bash
cd ~/flowguard
sudo bin/flowguard doctor   # expect no FAIL (as a normal user it reports that OVS/Mininet need root)
make test                   # unit + property tests (both venvs) + core API tests, ~75 s
make docs-check             # generated docs current
sudo make test-live         # live L1 + engine-to-core tests (root; ~50 s)
sudo make spike             # ~10 min, re-measures the Phase 0 feasibility results
```
As root from Windows: `wsl.exe -d Ubuntu-22.04 -u root -- bash -s < script.sh` (CLAUDE.md explains why not `bash -c '...$VAR...'`).

## Second laptop (native Ubuntu 22.04)
```bash
gh auth login && gh repo clone RKG765/flowguard ~/flowguard && cd ~/flowguard
sudo bash scripts/setup_ubuntu.sh && sudo bin/flowguard doctor
bin/flowguard keygen && make test && sudo make test-live
```
Unverified there: kernel datapath, OVS version differences in `ovs-ofctl monitor ... watch:!initial` output, Python 3.9 from the PPA. Record results in `docs/spike_findings.md` and `status.json` (environment entry).

## What to do next (Phase 3)
`STATUS.md` "Next 5 steps". The UI talks only to the core API documented in `ARCHITECTURE.md` ("Core API surface") and `/openapi.json`:
- auth: `POST /api/auth/login` returns `csrf_token` and sets the `fg_session` cookie; send `X-CSRF-Token` on every POST/PUT/PATCH; `GET /api/auth/me` returns the CSRF token again after a reload; `GET /api/setup/status` drives first-run onboarding.
- live: `POST /api/auth/ws-ticket` then `ws://127.0.0.1:8787/api/ws?ticket=...`; messages are `{type: hello|alert|alert_update|snapshot|engine_status|event, data}`.
- statuses for rule badges: `ok | altered | shadow | forged | missing | pending`; alert severities `low | medium | high`; incident statuses `open | acknowledged | closed`.
- Node 20 is installed in WSL (doctor checks it). Frontend stack per the brief: React + TypeScript + Vite, Tailwind, shadcn/ui, Framer Motion, TanStack Query, Zustand, Recharts/ECharts, React Flow, Lucide.

## Gotchas learned
- Python only from the venvs: `.venv-engine/bin/...` (Ryu, 3.9) and `.venv-core/bin/python` (core, lab, tests; sees apt Mininet).
- An unanswered "Create a default Unix user" prompt in any WSL terminal blocks every `wsl.exe` call.
- Windows reaches WSL as the default user (`rkg`); `/root` is not readable from Windows.
- Editing a file with Windows tools drops its exec bit (`bin/flowguard`, `scripts/*.sh`, `scripts/doctor.py`): `chmod +x` again.
- Mininet is root-only and has fixed names (`s1`, `h1`...): one lab at a time. A detached `nohup` job started through `wsl.exe` dies when that `wsl.exe` call returns; keep long jobs attached (background tool call).
- Test helper modules need unique names (`tests/api/apihelpers.py`): several `conftest.py` files exist.
- `ovs-ofctl monitor` output has no priority; the engine always re-reads the table (ADR-004).
- `config.yaml`, keys, `.scratch/` and runtime `data/core|engine|run|spool|sessions` are gitignored.
- No `Co-Authored-By` trailers in commits (owner instruction).
