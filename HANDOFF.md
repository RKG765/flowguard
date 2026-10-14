# Handoff: how to resume

Read `CLAUDE.md`, `STATUS.md`, then this file. Last rewritten at the end of Phase 1 (2026-10-14).

## Where things are
- Repo: `/home/rkg/flowguard` in WSL distro `Ubuntu-22.04` (user `rkg`). From Windows: `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`. Pointer + approved plan also in `D:\sds`.
- Branch `main`; `git log --oneline` for the commits (Phase 0, Phase 1). Remote `origin` = `git@github.com:RKG765/flowguard.git` (SSH). **Not pushed yet**: see "Push to GitHub".
- Next phase: **2, core service, API, storage, auth**. The owner must say "continue" first.

## Open the project
```powershell
wsl -d Ubuntu-22.04 --cd ~/flowguard          # as rkg (normal shell)
wsl -d Ubuntu-22.04 -u root --cd /home/rkg/flowguard   # as root, for Mininet/OVS tests
```

## Push to GitHub (owner action, one time)
A key was generated in WSL (`~/.ssh/id_ed25519`, no passphrase) and GitHub's host keys were pinned from api.github.com/meta. Print the public key and add it at https://github.com/settings/ssh/new :
```bash
cat ~/.ssh/id_ed25519.pub
ssh -T git@github.com            # expect: "Hi RKG765! You've successfully authenticated..."
cd ~/flowguard && git push -u origin main
```
The repository `RKG765/flowguard` must exist and be empty (no README/licence). On the native Ubuntu laptop: `git clone git@github.com:RKG765/flowguard.git` after adding that machine's own key.

## Start / stop things
The engine is run by the tests; there is no `flowguard start` yet (Phase 7). Manual run for experiments:
```bash
cd ~/flowguard
bin/flowguard keygen                                  # once; key at ~/.config/flowguard/hmac.key (0600)
sudo .venv-core/bin/python topo/topo_basic.py --hold  # lab (root), controller 127.0.0.1:6653
PYTHONPATH=. .venv-engine/bin/ryu-manager --ofp-tcp-listen-port 6653 engine.app
```
Start order does not matter (OVS keeps retrying the controller). `topo_basic.py` no longer runs Mininet's full cleanup by default because that kills every `ryu-manager` including the engine; pass `--clean` only when you want that. The live tests in `tests/integration/conftest.py` show the same setup. Open vSwitch is a system service: `systemctl status openvswitch-switch`. After an interrupted run: `sudo mn -c; pkill -f ryu-manager`.

## Verify the environment
```bash
cd ~/flowguard
bin/flowguard doctor        # expect no FAIL
make test                   # unit + property tests, both venvs
make docs-check             # generated docs current
sudo make test-live         # 14 live attack tests (needs root; ~30 s)
sudo make spike             # ~10 min, re-measures the Phase 0 feasibility results
```
As root from Windows: `wsl.exe -d Ubuntu-22.04 -u root -- bash -s < script.sh` (CLAUDE.md explains why not `bash -c '...$VAR...'`).

## Second laptop (native Ubuntu 22.04)
```bash
git clone git@github.com:RKG765/flowguard.git ~/flowguard && cd ~/flowguard
sudo bash scripts/setup_ubuntu.sh && bin/flowguard doctor
bin/flowguard keygen && sudo make test-live
```
Unverified there: kernel datapath, OVS version differences in `ovs-ofctl monitor ... watch:!initial` output, Python 3.9 from the PPA. Record results in `docs/spike_findings.md` and `status.json` (environment entry).

## What to do next (Phase 2)
`STATUS.md` "Next 5 steps". Contract already fixed by Phase 1: the engine writes alert JSON lines (`type: alert` and `type: alert_update`, each with `seq`) to `data/spool/alerts.jsonl` and publishes the same objects (plus `type: event`) on ZeroMQ PUSH to `ipc://<data>/run/events.ipc`; the core must bind a PULL socket there, store alerts, and acknowledge by writing the highest stored `seq` to `<spool>.ack` (the spool replays everything after it). Engine status for health: `data/run/engine_status.json`. Alert fields are visible in `results/phase1_live_alert_timings.json` and `engine/app.py`.

## Gotchas learned
- Python only from the venvs: `.venv-engine/bin/...` (Ryu, 3.9) and `.venv-core/bin/python` (lab, tests; sees apt Mininet).
- An unanswered "Create a default Unix user" prompt in any WSL terminal blocks every `wsl.exe` call (including mine).
- Windows reaches WSL as the default user (`rkg`); `/root` is not readable from Windows.
- Editing a file with Windows tools drops its exec bit (`bin/flowguard`, `scripts/*.sh`): `chmod +x` again.
- Mininet is root-only and has fixed names (`s1`, `h1`...): one lab at a time. A detached `nohup` job started through `wsl.exe` dies when that `wsl.exe` call returns.
- `ovs-ofctl monitor` output has no priority; the engine always re-reads the table (ADR-004).
- `ovs-vsctl -f csv` triple-quotes strings.
- `config.yaml`, keys and `.scratch/` are gitignored; `config.example.yaml` is the template.
- No `Co-Authored-By` trailers in commits (owner instruction).
