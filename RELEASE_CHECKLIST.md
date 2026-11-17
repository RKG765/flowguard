# Release checklist (prototype, 2026-11-17, second pass)

Every item states its evidence. Items without evidence stay unchecked with the reason.

- [x] All tests pass: core 224, engine 145, security 143, web 119, browser e2e 10, live lab 39 (commands and what they cover in `QA_REPORT.md`, 2026-11-17)
- [x] Measured results recorded and honest about limits: `docs/results.md` (`sudo make eval`: 40/40 detected, 0 false alerts), soak pass (`sudo make test-soak`, 60 s)
- [x] Accessibility checks pass: axe (WCAG 2 A/AA) on all 12 pages in both themes; contrast of every text token unit-tested
- [x] AI-simulated security, code and design reviews done; every high and medium finding fixed and re-tested (`SECURITY_REVIEW.md`, `UX_REVIEW.md`)
- [x] Documented limits and residual risks listed (`SECURITY_REVIEW.md`, `UX_REVIEW.md`, `docs/results.md`, `STATUS.md`)
- [x] One-command start works on WSL2: `sudo bin/flowguard start`, `status`, `stop`, `export` (checked 2026-11-17)
- [ ] **No open blocker or high findings:** none known after the fixes, but no human review has happened, and the design review's last fixes were verified by tests, not by a final screenshot round
- [x] **Clean install from `setup_ubuntu.sh`:** `sudo bash scripts/pristine-check.sh` built a clean Ubuntu 22.04 userland, ran the setup script, `doctor --quick` (12 pass, 0 fail), core tests 224 passed, engine tests 145 passed, web 119 passed and the build (`results/pristine_install.txt`). Limits: it is a chroot on the WSL2 kernel (the Open vSwitch lab is not re-tested there), and because the deadsnakes PPA was down, packages already downloaded on this machine seeded the apt cache
- [x] **Phase 6 remainder:** PDF reports and in-browser session replay built and tested
- [x] **Phase 7 remainder:** engine and core run as separate unprivileged accounts (`tests/integration/test_least_privilege_live.py`)
- [x] **Phase 9 remainder (part):** reconnect storm, wiped table, engine restart, 303-rule load, rule flood and two switches tested live
- [ ] **Phase 9 still open:** SQLite corruption, more than two switches, real hardware
- [ ] **Second-laptop (native Ubuntu) re-test:** not run; steps are `RUN_AND_SHOW.md` sections 1 to 4
- [ ] **Threat-model coverage map complete:** not written; `docs/threat_model.md` predates Phases 5 to 7
- [ ] **No open blocker or high findings:** none known, but no human review has happened and the second-pass code had no second AI reviewer
