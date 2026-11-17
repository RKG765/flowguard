# Release checklist (prototype, 2026-11-17)

Every item states its evidence. Items without evidence stay unchecked with the reason.

- [x] All tests pass: core 218, engine 141, security 137, web 116, browser e2e 10, live lab 26 (commands and what they cover in `QA_REPORT.md`, 2026-11-17)
- [x] Measured results recorded and honest about limits: `docs/results.md` (`sudo make eval`: 40/40 detected, 0 false alerts), soak pass (`sudo make test-soak`, 60 s)
- [x] Accessibility checks pass: axe (WCAG 2 A/AA) on all 12 pages in both themes; contrast of every text token unit-tested
- [x] AI-simulated security, code and design reviews done; every high and medium finding fixed and re-tested (`SECURITY_REVIEW.md`, `UX_REVIEW.md`)
- [x] Documented limits and residual risks listed (`SECURITY_REVIEW.md`, `UX_REVIEW.md`, `docs/results.md`, `STATUS.md`)
- [x] One-command start works on WSL2: `sudo bin/flowguard start`, `status`, `stop`, `export` (checked 2026-11-17)
- [ ] **No open blocker or high findings:** none known after the fixes, but no human review has happened, and the design review's last fixes were verified by tests, not by a final screenshot round
- [ ] **Clean install from `setup_ubuntu.sh` on a pristine machine:** not tested (only re-runs on this partly provisioned WSL2)
- [ ] **Threat-model coverage map complete:** not written; `docs/threat_model.md` predates Phases 5 to 7
- [ ] **Second-laptop (native Ubuntu) re-test:** not run; steps are `RUN_AND_SHOW.md` sections 1 to 4
- [ ] **Phase 6 remainder:** PDF reports and session replay are not built
- [ ] **Phase 7 remainder:** engine and core still run as root in the lab (no separate OS users)
- [ ] **Phase 9 remainder:** reconnect storms, SQLite corruption, rate limits live, many switches, load: not tested
