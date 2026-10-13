> **Approved by the owner on 2026-10-14 with changes.** The approved decisions (repo in WSL, dpid+epoch bound HMAC, os-ken fallback, alert spool limits, table layout, milestone tags) are recorded in `DECISIONS.md`. Where this plan and `DECISIONS.md` differ, `DECISIONS.md` wins. Milestone tags: `demo-v0` after Phase 4, `novelty-complete` after Phase 5.

# FlowGuard: implementation plan (for review, nothing built yet)

Status: DRAFT awaiting your approval. No product code has been written. Only read-only checks were run on this machine.

## 1. What I found on this machine (checked 2026-10-14)

| Item | Finding | Consequence |
|---|---|---|
| `D:\sds` | Empty, not a git repo | Clean start |
| WSL2 | `Ubuntu-22.04` installed (WSL2, systemd enabled in `/etc/wsl.conf`), kernel `6.6.87.2-microsoft-standard-WSL2` | Matches the target; `systemd` units usable here |
| Kernel config | `CONFIG_OPENVSWITCH=m`, `CONFIG_NET_SCH_HTB=m`, `CONFIG_NET_SCH_NETEM=m` | The module is *built*; whether the `.ko` is actually shipped and loadable is unproven. Phase 0 must test `modprobe openvswitch`. Fallback: userspace datapath (`datapath_type=netdev`) |
| Python in WSL | 3.10.12 only | Ryu needs 3.9 (see risks); install 3.9 via deadsnakes in `setup_ubuntu.sh` |
| OVS, Mininet, Ryu, Node in WSL | None installed | `setup_ubuntu.sh` installs them (Node 20 via NodeSource) |
| Windows side | git, Node, Python 3.10 present | Only used as a viewer (browser); the whole product runs in WSL |
| Disk | 190 GB free on D:, 954 GB in the WSL disk | No constraint |
| Root in WSL | `uid 0` by default | Easy for the lab, but I will still build the privileged helper as a separate allowlisted process, as specified |

## 2. One decision I need from you (the only blocker)

**Where does the repo live?**
- **Recommended: inside WSL (`~/flowguard`, ext4).** Reasons: `chmod 0600` for the HMAC key works, `npm install` and SQLite WAL are far faster, git file modes behave. I would still work on it from here through `\\wsl.localhost\Ubuntu-22.04\home\<user>\flowguard`, and `D:\sds` keeps this plan plus a pointer file.
- Alternative: keep it in `D:\sds` (accessed as `/mnt/d/sds`). Slow, no real permissions, SQLite WAL is unreliable on the `/mnt` mount. I would not do this for the running system.

## 3. Proposed deviations and clarifications (tell me if you disagree)

1. **Bind `dpid` into the HMAC input.** Your canonical form (table, priority, match, instructions) would let a valid cookie be reused on the same rule on another switch. Adding `dpid` closes that and matches the "reuse on a different switch" adversary test. The cookie format stays `(tag48 << 16) | epoch16`.
2. **Honest limit on L1:** a tamper-and-revert faster than the poll/monitor interval can be missed, and a root attacker on the *same* host as the key can read it. Both go in the threat model and the results, not hidden.
3. **Google Stitch:** I have no access to it. In Phase 3 I will give you the exact brief text to paste; if you do not use it I implement from the brief directly and say so.
4. **Ryu runtime:** Python 3.9 venv, `ryu==4.34`, `eventlet==0.30.2` (the combination known to work). Confirmed or replaced by the Phase 0 spike, recorded in `docs/spike_findings.md`.
5. **IPC engine -> core:** ZeroMQ PUSH/PULL over a Unix socket. In Ryu, events go into a bounded in-memory queue drained by one green thread using `zmq.green`; on overflow events are dropped *and counted* (visible health metric), the Ryu loop never blocks. Alerts also go to an append-only local spool file first so nothing is silently lost if the core is down.
6. **PDF reports:** `reportlab` (no browser dependency). Charts: Recharts. WebSocket auth: short-lived ticket from the REST login session.
7. **Tests of long duration** (Phase 8 repeats, Phase 9 soak of several hours) need the PC to stay awake; I will ask for keep-awake at that point.

## 4. Architecture as I will build it

```
 Windows browser --http://localhost:PORT--> [core: FastAPI+Uvicorn, non-root, serves built React app]
                                              |  SQLite(WAL), risk engine, auth, audit, WS
        ZeroMQ (events, bounded, non-blocking)|            ^ unix socket + token (allowlisted calls only)
 [Ryu app: signer, L1 verifier, L2 prober, responder] <-OpenFlow:6653-> [OVS + Mininet hosts]
                                              |                          ^
                              [ML worker proc]                 [privileged helper (root): topo manager,
                                                                attack runner A1-A7, lab-switch guard]
```

Processes: `ryu-engine` (py3.9 venv), `core` (py3.10 venv), `ml-worker`, `helper` (root, tiny, allowlist), `web` (static build served by core, single port). Only the helper is privileged. All run under systemd units when available, otherwise `flowguard start|stop|status`.

## 5. Phases: deliverables and exit criteria

Every phase ends with: tests run, all affected docs + `status.json` updated, `make docs-check` passing, one commit, a summary (works / does not / simulated), then STOP for your "continue".

| # | Phase | Main deliverables | Exit criteria (must be shown by a real command) |
|---|---|---|---|
| 0 | Doctor + feasibility spike | Repo skeleton; all 7A docs (initial), `status.json`, `update_docs.py`, `make docs/docs-check`; `doctor.sh` + `flowguard doctor`; `setup_ubuntu.sh`; `topo_basic.py` (1 switch, 4 hosts, optional 2nd switch); `docs/spike_findings.md` | OVS datapath mode known (kernel vs netdev); Mininet ping passes; Ryu learning switch works; flow-monitor (OF1.4 `OFPMP_FLOW_MONITOR` and OVS NXST) tested; targeted `OFPFlowStatsRequest` by table tested; L1 mode chosen (event-driven or polling) with evidence |
| 1 | Engine L1 | `canonical`, `crypto`, golden store, `install_signed_rule()`, verifier (forged/altered/shadow/missing/ok, grace window), responder (restore, rate limit), detection timing | Unit + property tests green; Mininet integration test: tamper with `ovs-ofctl`, rule detected and restored, time recorded |
| 2 | Core service | FastAPI, Alembic migrations, ingest, all REST resources, WebSocket, argon2 auth + roles, audit log, OpenAPI | API tests incl. role matrix; ingest from a real engine; WS stream verified |
| 3 | Design system + shell | Tokens, glass components, app shell, Ctrl+K palette, theme toggle, `/design` style guide, Stitch brief for you | Playwright smoke; contrast check on glass surfaces; reduced-motion/transparency fallbacks |
| 4 | Attack Lab + core pages | Overview, Topology, Rule Inspector, Alerts/Incidents, Attack Lab; helper with A1-A6; before/after diff, timing | Playwright: login, run A1, alert appears live, rule restored. First screenshots into `docs/img/` |
| 5 | L2 + L3 + risk | PacketOut canaries, A7 (SIMULATED lying switch), own dataset from Mininet, IsolationForest vs OC-SVM, ML worker, risk fusion + dry-run | A7 missed by L1, caught by L2 (live); A6 scored by L3; ML metrics stored from a held-out evaluation |
| 6 | Remaining pages | Probes, ML, Policy, Reports (PDF/CSV), Audit, Users, Settings (+ "About and build status") | Page-by-page Playwright; empty/loading/error states |
| 7 | Packaging + hardening | `make` targets, `flowguard` CLI, single-port prod build, auth rate limit, CSRF/CORS, helper allowlist tests, dep audit, clean-install test | Clean-install from scratch on WSL passes; `docs/user_guide.md` for the second laptop |
| 8 | Evaluation | A1-A7 x >=30 runs, churn run, overhead (monitor off/on), CPU, time-to-restore, ML P/R/F1, ablation L1 / L1+L2 / L1+L3 / all | `docs/results.md` with measured numbers only, each tied to a file in `data/` or `results/`; Reports page shows them |
| 9 | Rigorous QA | Unit/property (Hypothesis), integration, E2E + visual regression, chaos, load/soak, race/timing, security automation, compatibility, a11y (axe), doc-following test | `TESTING.md` + `QA_REPORT.md` with real output, coverage, tracked issues |
| 10 | Persona reviews | AI-simulated consumer review (`UX_REVIEW.md`) and SOC/adversary review (`SECURITY_REVIEW.md`), both labelled as AI-simulated with real human testing recommended | Reports + screenshots in `docs/img/review/`, findings tables, threat-model coverage map |
| 11 | Fix loop + release gate | Fixes for blocker/high (+ practical medium) with regression tests, retests, filled `RELEASE_CHECKLIST.md`, RC tag | Gate evaluated honestly; failures stay unchecked with reasons; list of items to re-run on native Ubuntu |

## 6. Phase 0 plan (the part you asked to see before any code, under 15 lines)

1. Create the repo (in the location you choose), `git init`, skeleton per section 7 of your brief.
2. Create all 7A docs as initial versions, `docs/graphs/status.json`, `scripts/update_docs.py`, `make docs` / `make docs-check`.
3. Write `scripts/setup_ubuntu.sh`: apt packages (openvswitch-switch, mininet, python3.9 via deadsnakes, build deps), Node 20, venvs, pinned versions.
4. Detect environment (`wsl` vs `ubuntu`) and start the OVS daemons (systemd if present).
5. Spike A: `modprobe openvswitch`; if it fails, switch to `datapath_type=netdev` and record why.
6. Spike B: Mininet topology (1 switch, 4 hosts) and a `pingall`; check tc/netem usage.
7. Spike C: Ryu 4.34 on Python 3.9 with a learning switch controlling OVS.
8. Spike D: flow monitor via OF1.4 `OFPMP_FLOW_MONITOR` and OVS `NXST_FLOW_MONITOR`; targeted `OFPFlowStatsRequest(table_id=...)`; measure latency of an external `ovs-ofctl mod-flows` being noticed.
9. Write `scripts/doctor.sh` and `flowguard doctor` (PASS/FAIL table with fixes).
10. Write `docs/spike_findings.md` with command output as evidence; choose L1 mode; record in `DECISIONS.md`.
11. Update `STATUS.md`, `HANDOFF.md`, `CLAUDE.md`, `status.json`; run `make docs-check`; commit.
12. Print the summary, then STOP and wait for "continue".

## 7. Risks, ranked

| Risk | Likelihood | Mitigation |
|---|---|---|
| OVS kernel module not loadable in the WSL kernel | Medium | Userspace datapath fallback (`netdev`), documented in `DECISIONS.md`. Custom kernel only as a last resort with exact steps |
| Ryu 4.34 does not run cleanly on newer Python/eventlet | High if wrong Python | Python 3.9 venv, pinned `eventlet`; spike proves it before Phase 1 |
| Flow monitor not exposed usefully through Ryu | Medium | Polling by `table_id` at a configurable interval; then report detection probability vs interval honestly |
| Mininet `tc` features missing on WSL kernel | Low-Medium | Avoid shaped links (use plain links) and note it |
| Scope: this brief is months of work for a team | Certain | Strict phase gating; each phase is independently runnable and verified; nothing marked `done` without its command having run |
| Long soak/evaluation runs interrupted by sleep | Medium | Request keep-awake; the session recorder lets runs resume |

## 8. Working rules I will follow

- Read `CLAUDE.md`, `STATUS.md`, `HANDOFF.md` first in every session.
- No number appears in a UI or doc without a source file; simulated things are badged SIMULATED.
- I will not describe the product as "secure", "fully tested" or "production-ready".
- Attacks only ever target the lab switch the helper created itself.
