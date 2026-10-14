# Architecture decisions

Format: context, decision, alternatives, consequences. Status is `accepted` unless noted. Evidence files are in `docs/spike_evidence/`.

## ADR-001: Repo lives on the WSL ext4 filesystem, in the default user's home
- **Context:** The development machine is Windows 11 + WSL2; the product needs `chmod 0600` key files, fast `npm install`, and SQLite WAL.
- **Decision:** Repo at `~/flowguard` = `/home/rkg/flowguard` (owner `rkg`). Windows access via `\\wsl.localhost\Ubuntu-22.04\home\rkg\flowguard`. `D:\sds` holds the plan and a pointer file only. Remote: `https://github.com/RKG765/flowguard.git` over HTTPS, authenticated with the GitHub CLI device flow (an SSH key was generated first but not used; GitHub never received it).
- **History:** Phase 0 and the start of Phase 1 lived in `/root/flowguard` while root was the only WSL user. When the owner created the default user `rkg`, Windows (which reaches the distro as the default user) could no longer read `/root`, so the repo was moved to `/home/rkg/flowguard` and the venvs were rebuilt.
- **Alternatives:** `/mnt/d/sds` (slow, no real permissions, unreliable SQLite WAL).
- **Consequences:** Mininet/OVS tests run as root against an rkg-owned repo (root has `safe.directory`); the privilege-separated services (non-root core, root helper) are tested in Phases 2/7 with a dedicated service user.

## ADR-002: Separate processes; ZeroMQ between engine and core
- **Context:** Ryu runs on eventlet, FastAPI on asyncio; the Ryu loop must never block.
- **Decision:** Separate processes. Engine -> core over ZeroMQ PUSH/PULL on a Unix socket. In Ryu, events go into a bounded in-memory queue drained by one green thread that sends with `zmq.NOBLOCK` (plain pyzmq is safe because a non-blocking send never waits; `zmq.green` is gevent-specific); on overflow events are dropped and counted (`events_dropped_total`, a health metric). The web server never runs as root; the privileged helper is its own small process with a command allowlist.
- **Alternatives:** local HTTP + queue (heavier, more failure modes), shared SQLite (couples the two loops).
- **Consequences:** `pyzmq` in the engine venv (pinned, installed and import-checked by `flowguard doctor`). Status: engine side implemented and unit-tested in Phase 1 (`engine/channel.py`, real ZeroMQ PUSH/PULL tests); the core (PULL) side and the ack path arrive in Phase 2.

## ADR-003: Ryu 4.34 on Python 3.9 with pinned build tooling; os-ken is the fallback
- **Context:** Ryu 4.34 does not install/run cleanly on current tooling.
- **Decision:** `.venv-engine` on Python 3.9 (deadsnakes) with `pip==23.3.2`, `setuptools==58.0.0`, `ryu==4.34`, `eventlet==0.30.2`, `dnspython==1.16.0`, `pyzmq==26.2.0`. Full resolved set: `requirements/engine.lock.txt`. Verified: `ryu-manager --version` -> 4.34, and the spike controller runs and controls OVS (`docs/spike_evidence/`).
- **Fallback (not used):** `os-ken` (the maintained fork of Ryu used by OpenStack) if Ryu 4.34 breaks on a future toolchain. API is nearly identical (`os_ken` namespace). Switching would be recorded as a new ADR.
- **Consequences:** Python 3.9 comes from a PPA, so the setup script must add it (ADR-010).

## ADR-004: L1 detection is event-driven via an OpenFlow 1.0 Nicira monitor session, confirmed by a targeted stats request
- **Context:** Spike results (`docs/spike_findings.md`): OVS 2.17.12 rejects the standard OF1.4 `OFPMP_FLOW_MONITOR` and rejects `NXST_FLOW_MONITOR` over OpenFlow 1.3 (`OFPBRC_BAD_SUBTYPE`). `NXST_FLOW_MONITOR` works over an OpenFlow 1.0 session. Polling table 0 at 0.5 s missed every tamper-and-revert done within one `ovs-ofctl` pair; the monitor saw all of them.
- **Decision:** Mode = **event-driven**. Each lab switch exposes a passive OpenFlow port (`ptcp:6634+`). The engine runs a monitor session (`ovs-ofctl monitor tcp:127.0.0.1:<port> watch:` supervised as a subprocess in Phase 1) as a *trigger*. A trigger for a critical table causes a targeted `OFPFlowStatsRequest(table_id=...)` over the controller's OF1.3 connection, which is the ground truth the verifier checks against signed rules. A slow reconciliation poll (configurable, default 5 s) remains as a safety net for monitor drops.
- **Alternatives:** polling only (simpler, misses fast revert); OF1.4 monitor (not supported by this OVS); a native Python NXST client (more code; revisit if text parsing proves fragile).
- **Consequences:** If the attacker reverts before the confirming stats request, the table already matches the golden rules, so state comparison alone says "ok". The verifier therefore also raises `unattributed_change` for any critical-table event not explained by the engine's own FlowMods (tracked via the pending set). The monitor text format is parsed (events ADDED/DELETED/MODIFIED with table and cookie; priority is not printed). Limitation to document: events do not carry instructions, hence the confirm step. Whether the same holds on the native Ubuntu laptop's OVS build is `unverified` until re-run there.
- **Implemented in Phase 1** (`engine/app.py`, `engine/monitor_parser.py`): the monitor is `stdbuf -oL ovs-ofctl monitor tcp:127.0.0.1:<port> watch:!initial` (`!initial` skips the initial flow dump, found in the man page); the supervisor restarts it with backoff and raises `monitor_down`. `unattributed_change` is raised when a critical-table event leaves the table equal to the golden rules. Live evidence: `tests/integration/test_l1_live.py`, `results/phase1_live_alert_timings.json`.

## ADR-005: HMAC input binds dpid and epoch; short rotation window
- **Decision:** `tag = first 48 bits of HMAC-SHA256(K_epoch, canonical_bytes)` where `canonical_bytes` covers (dpid, epoch16, table_id, priority, normalized match, normalized instructions) and excludes counters, durations, timeouts, flags and the cookie. `cookie = (tag << 16) | epoch16`. `K_epoch = HMAC-SHA256(master_key, "flowguard-epoch" || epoch16)` so old epochs can be re-derived. After rotation the previous epoch is accepted for `rotation_grace_seconds` (config, default 300) and then rejected. dpids are explicit in the Mininet topology (`s1=0000000000000001`, `s2=0000000000000002`).
- **Why dpid:** otherwise a valid cookie could be reused on the same rule on a different switch.
- **Implemented in Phase 1** (`engine/canonical.py`, `engine/crypto.py`; unit + Hypothesis tests; live rotation test). The key file must be mode 0600 and owned by the current user or the engine refuses to start; the environment variable `FLOWGUARD_HMAC_KEY` is the alternative.
- **Consequences:** 48-bit tag: forgery needs 2^47 expected online guesses against a verifier that restores on first sight; the realistic attack is copying/replaying, which the binding addresses. Status `planned` (Phase 1).

## ADR-006: Table layout
- **Decision:** Table 0 = security/ACL rules (miss -> `goto_table:1`). Table 1 = learning-switch rules (miss -> controller). `critical_tables` defaults to `[0]`. Verified in the spike: pingall 0% loss with this pipeline on OF1.3 and OF1.4.
- **Consequences:** Tampering with table 1 is out of L1 scope by default (configurable).

## ADR-007: OVS datapath
- **Decision:** `auto`: use the kernel datapath when `/sys/module/openvswitch` exists (or `modprobe` succeeds), otherwise the userspace datapath (`datapath_type=netdev`). On this WSL2 kernel (6.6.87.2) the kernel module loads and both datapaths work (`docs/spike_evidence/s1_datapath.txt`), so no custom kernel is needed.
- **Consequences:** The userspace path is exercised by `make spike` so the fallback is known to work when a machine lacks the module.

## ADR-008: Everything Python runs in a venv
- **Decision:** `.venv-engine` (3.9) for Ryu; `.venv-core` (3.10, `--system-site-packages`, because apt installs Mininet's module system-wide) for the lab, helper, core and tests. `bin/flowguard` and `scripts/doctor.py` use only the standard library so they work before venvs exist.

## ADR-009: Alert spool (no silent alert loss)
- **Decision (implemented in Phase 1, `engine/spool.py`):** Every alert is appended to `data/spool/alerts.jsonl` (fsync) before it is sent over ZeroMQ; the core acknowledges by sequence number. Unacknowledged records are replayed on reconnect. Rotation at 10 MiB per file, keep 5 files (50 MiB cap). When the cap is reached the oldest file is dropped, `spool_dropped_total` is incremented and a synthetic `spool_overflow` alert is emitted. All three numbers are in `config.example.yaml`. A torn last line left by a crash is healed on open (regression test).

## ADR-010: Deadsnakes PPA is added manually
- **Context:** `add-apt-repository` needs `api.launchpad.net`, which timed out from this machine (`docs/spike_evidence/setup_run1.log`), while the PPA mirror and keyserver are reachable.
- **Decision:** `setup_ubuntu.sh` fetches the signing key from `keyserver.ubuntu.com`, checks its fingerprint (`F23C5A6C...5776`), and writes a `signed-by` source entry itself.

## ADR-011: The engine's own changes are attributed by cookie, but in-flight rules are exempted by SLOT
- **Context:** The engine's own FlowMods produce monitor events and briefly make the switch differ from the golden store. The first Phase 1 live run showed that exempting rules by *cookie* let an attacker copy a golden cookie onto a different rule and hide inside the grace window (it was only caught 2 s later by the reconcile poll).
- **Decision:** `Pending` records, for every FlowMod the engine sends, the cookie (to attribute the monitor event) and the rule slot `(table, priority, canonical match)` (to defer judgement). `classify(..., skip_slots=...)` skips only those slots. Every attributed event also schedules a verification pass after the grace window, because attribution by cookie can be spoofed. A pass scheduled earlier supersedes a slower queued pass, so a live event is never held back by a delayed confirmation pass.
- **Consequences:** Regression tests: `test_copying_a_golden_cookie_cannot_hide_inside_the_grace_window` and the live `test_a5_cookie_copied_from_a_valid_rule_...`. Known residual limit: an attacker who changes the *same slot* the engine is touching within the grace window (default 500 ms) is judged only after the window; the post-grace pass and the reconcile poll cover that. To be measured in Phase 9.

## ADR-012: Repair semantics and classification
- **Repair:** Restore and re-sign use `OFPFC_ADD`, which atomically replaces a rule with the same table/priority/match (no window where the rule is absent). Forged and shadow rules are removed with `OFPFC_DELETE_STRICT`. Nothing is deleted when a rule cannot be normalized (`unparseable_rule`: alert only). Repairs are limited per switch per minute (`restore_rate_limit_per_minute`, default 30) and then become alerts (`restore_rate_limited`). `response_mode: alert_only` is the dry run.
- **Classes:** `missing` (golden rule absent), `altered` (same slot, different instructions or cookie), `shadow` (not golden, equal or higher priority, overlaps a protected rule; golden table-miss rules are ignored for this test because they overlap everything), `forged` (any other non-golden rule). `signature_valid` is reported for non-golden rules so a replayed old signed rule is visible as such.

## ADR-013: Core ingest = ZeroMQ fast path + ordered spool tail, acknowledgement by in-order sequence
- **Context:** The engine must never block on the core, and no alert may be lost silently (ADR-002, ADR-009).
- **Decision:** The core binds a ZeroMQ PULL socket at `ipc://<data>/run/events.ipc` (fast path) and, in the same thread, tails the engine's spool files oldest-first from the last processed sequence (guaranteed path). Every record type is idempotent (alerts by id, updates once, snapshots only if newer), so receiving an alert on both paths is harmless. Only the spool tail acknowledges: it writes the highest sequence it has processed IN ORDER to `<spool>.ack`, so a gap is never acknowledged. Half-written last lines are left for the next poll. The ingest thread is the database's only writer for engine data.
- **Engine additions:** after each verification pass the engine publishes a per-rule `snapshot` of the table (statuses ok/altered/shadow/forged/missing/pending), only when it changed or every 10 s, plus an `engine_status` object every 5 s.
- **Consequences:** The core needs read access to the spool and write access to its `.ack` file (same data dir in the lab; separate users and a shared group in Phase 7). Verified: `tests/api/test_ingest.py`, `tests/integration/test_core_live.py`.

## ADR-014: Core authentication and authorization
- **Decision:** Local accounts with argon2id hashes; opaque 256-bit session tokens of which only the SHA-256 is stored; HttpOnly `SameSite=Strict` cookie for the browser plus `Authorization: Bearer` for API clients; a per-session CSRF token required in `X-CSRF-Token` on every state-changing cookie request; roles `viewer < analyst < admin` enforced by a dependency on every route; login lockout per (IP, username); one-time WebSocket tickets; first-run setup creates the only bootstrap admin and is refused once any user exists; the last active admin cannot be demoted or disabled; any change to a user revokes their sessions.
- **Alternatives:** JWTs (not revocable without a server-side list anyway), OAuth (out of scope for a local lab product).
- **Consequences:** The login limiter is in memory (resets on restart; documented). A test enumerates every route and fails when an unclassified route appears (`tests/api/test_roles.py`).

## ADR-015: Hash-chained audit log
- **Decision:** Each audit row stores `sha256(prev_hash + canonical row)`; `GET /api/audit/verify` (admin) recomputes the chain. User-agent, username and target are stripped of control characters (no log injection). Denials (403) are logged; 401s are not (anonymous noise).
- **Limit:** Someone with write access to the database file can rewrite the whole chain from the first edited row onwards; the chain proves a row was changed in place, not that the file is authentic. An external anchor (e.g. periodically exported head hash) is backlog.

## ADR-016: Policy document stored now, enforced later
- **Decision:** `GET/PUT /api/policies` stores a validated, versioned policy (risk weights, ordered thresholds, actions per severity, critical tables, dry run) with history and audit. Every response carries `enforced: false` until the Phase 5 risk engine reads it; the engine still uses `config.yaml` / its policy file today.
