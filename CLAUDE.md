# CLAUDE.md: project memory for FlowGuard

**First, in every session (including a fresh one on another machine): read `STATUS.md` and `HANDOFF.md`, then continue from there. Do not ask the owner to re-explain.**

## What this is
FlowGuard detects unauthorized changes to OpenFlow flow rules in SDN (Ryu + Open vSwitch), explains them, and responds safely. Three layers: L1 authenticated rules (HMAC in the 64-bit cookie), L2 data-plane canary probing, L3 ML anomaly scoring; a risk engine fuses them. ML alone never deletes rules. The full brief is the owner's "Claude Code prompt v2"; the agreed plan is `D:\sds\IMPLEMENTATION_PLAN.md` (Windows side) and `DECISIONS.md` (here).

## Phases (stop after each and wait for the owner's "continue")
0 doctor+spike, 1 engine L1, 2 core service, 3 design system, 4 Attack Lab (tag `demo-v0`), 5 L2+L3+risk (tag `novelty-complete`), 6 pages, 7 packaging, 8 evaluation, 9 QA, 10 persona reviews, 11 fix loop + release gate. Current phase: see `STATUS.md`.

## Repo map
`engine/` Ryu app (signer, verifier, prober, responder) | `core/` FastAPI service | `helper/` privileged helper (allowlist) | `topo/` Mininet topology | `attacks/` A1-A7 | `web/` React app | `scripts/` setup, doctor, update_docs, spikes | `docs/` threat model, spike findings, graphs | `tests/` unit, integration, e2e | `data/` sessions, models (gitignored).

## Commands
`make setup` | `make doctor` | `make docs` / `make docs-check` | `make test` (unit+property, both venvs) | `make test-live` (root; real OVS+Mininet+engine) | `make keygen` | `make spike`. Not implemented yet: `make start demo eval test-e2e test-security test-soak` (they exit 2 on purpose).

## Environment facts (verified, see `docs/spike_findings.md`)
- Repo lives in WSL at `/home/rkg/flowguard` (default user `rkg`, created by the owner on 2026-10-14; the repo was moved there from `/root/flowguard` because Windows reaches the distro as `rkg` and `/root` is private). Edit from Windows via `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`.
- Mininet/OVS need root: run those with `wsl.exe -d Ubuntu-22.04 -u root -- ...` (root has `safe.directory` for the repo). Keep files owned by rkg (`chown -R rkg:rkg .` after root runs). Editing a file from Windows drops its exec bit: re-`chmod +x bin/flowguard scripts/*.sh` after editing one.
- **All Python runs in a venv**: `.venv-engine` (Python 3.9, Ryu 4.34, pinned) and `.venv-core` (system 3.10, `--system-site-packages` so it sees apt Mininet). The stdlib-only `bin/flowguard` and `scripts/doctor.py` may run on system python.
- When calling `wsl.exe ... bash -c '...'` from Windows tools, the command string is re-parsed by a shell: `$VAR` is expanded early. Put non-trivial commands in a script file and run it, or pipe on stdin (`wsl.exe -d Ubuntu-22.04 -u root -- bash -s < script`). An unanswered first-run prompt ("Create a default Unix user") in any WSL terminal blocks every `wsl.exe` call.
- `api.launchpad.net` is unreachable from this machine: PPAs are added by hand (see `setup_ubuntu.sh`).

## Engineering rules (non-negotiable)
1. Never mark anything `done`/"works" unless the verifying command ran in this session; record command + date in `docs/graphs/status.json`.
2. Every number in docs/UI cites a source file in `data/` or `results/`. No source, no number. Simulated things are badged SIMULATED.
3. Anything unbuilt is labelled `planned`. Never describe it as working.
4. Update all affected docs at the end of every phase and before every STOP; commit docs with the code. `make docs-check` must pass.
5. Type hints, docstrings, small functions, structured JSON logging. Tests ship with the feature; every bug fix ships with a regression test.
6. No secrets in the repo. HMAC key lives outside the repo (0600 file or env var).
7. Attacks only target the lab switch the helper created itself; helper accepts allowlisted attack IDs only; no arbitrary shell from the web layer.
8. Never claim the product is "secure", "fully tested" or "production-ready". Persona reviews are AI-simulated and must say so.
9. If context is running low, update `STATUS.md` and `HANDOFF.md` first.
10. Owner instruction: never add `Co-Authored-By` trailers or any Claude attribution to commits or PR text.
11. Git remote is `https://github.com/RKG765/flowguard.git`, authenticated with `gh` (done). Push as user `rkg`. Never ask for or handle tokens or passwords; if auth breaks, start `gh auth login --web` and give the owner the one-time code and link.
