# Handoff: how to resume

Read `CLAUDE.md`, `STATUS.md`, then this file. Last rewritten at the end of Phase 0 (2026-10-14).

## Where things are
- Repo: `/root/flowguard` in WSL distro `Ubuntu-22.04` (user `root`). From Windows: `\\wsl.localhost\Ubuntu-22.04\root\flowguard`. Pointer + approved plan also in `D:\sds`.
- Branch `main`; see `git log --oneline` for the Phase 0 commit. No GitHub remote yet.
- Next phase: **1, engine L1**. The owner must say "continue" first.

## Start / stop services
Nothing FlowGuard-specific runs yet (`flowguard start|stop|status` are planned, Phase 7). Only Open vSwitch is a system service:
```bash
systemctl status openvswitch-switch      # WSL2 has systemd enabled
sudo systemctl restart openvswitch-switch
```
The spikes start and stop their own Ryu and Mininet processes. If a run is interrupted: `mn -c` and `pkill -f ryu-manager`.

## Verify the environment
```bash
cd /root/flowguard
bin/flowguard doctor        # expect no FAIL
make test                   # unit tests (.venv-core)
make docs-check             # generated docs current
sudo make spike             # ~10 min, re-measures the L1 feasibility results
```

## Setting up on the second laptop (native Ubuntu 22.04)
```bash
git clone <your GitHub remote> flowguard && cd flowguard
sudo bash scripts/setup_ubuntu.sh
bin/flowguard doctor
sudo make spike            # compare docs/spike_evidence with the WSL2 numbers
```
Things to check there that are unverified: kernel datapath, OVS version, whether `ovs-ofctl monitor` over OF1.0 behaves the same, Python 3.9 PPA install. Record results in `docs/spike_findings.md` and `status.json` (environment entry).

Add the remote and push (owner action):
```bash
git remote add origin <url> && git push -u origin main --tags
```

## What to do next (Phase 1)
See `STATUS.md` "Next 5 steps" and `DECISIONS.md` ADR-004/005/009. Design requirements already agreed: HMAC binds dpid and epoch; previous epoch accepted for `rotation_grace_seconds`; table 0 critical; `unattributed_change` for events the engine did not cause; alert spool 10 MiB x 5.

## Gotchas learned
- Run Python only from the venvs: `.venv-engine/bin/...` (Ryu, Python 3.9) and `.venv-core/bin/python` (lab, tests; it sees apt Mininet).
- Mininet and the spikes need root and clean up with `mn -c`; only one lab at a time (fixed names `s1`, `h1`...).
- Passing `$VAR` through `wsl.exe -- bash -c` breaks; use script files.
- `ovs-vsctl -f csv` triple-quotes strings.
- `ovs-ofctl monitor` text output has no priority field.
- `config.yaml`, keys and `.scratch/` are gitignored; `config.example.yaml` is the template.
- The WSL default user is root, so privilege separation (non-root core, root helper) must be tested deliberately in Phases 2 and 7.
