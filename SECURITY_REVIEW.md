# Security review (Phases 5 to 7 changes)

**This is an AI-simulated review.** Two independent AI reviewers (a security reviewer and a code reviewer, each in a fresh
context, read-only) examined the uncommitted Phase 5 to 7 changes on 2026-11-17, and every finding below was checked against
the code before it was fixed. It is not a penetration test and not a statement that FlowGuard is secure. The pre-implementation
threat model is `docs/threat_model.md`; the lab limitation stands (controller, key and switch share one host, so an adversary
who controls that host defeats the product).

## What was reviewed
`engine/app.py` (L2 probes, quarantine, risk decision, control files), `engine/prober.py`, `engine/risk.py`,
`engine/anomaly.py`, `core/api/admin_api.py`, `core/ingest.py`, `scripts/prototype.sh`, `bin/flowguard`, `scripts/eval.py`,
`web/src/pages/Admin.tsx`, `Demo.tsx`, `ui/streamlit_app.py`.

## Findings and what was done
| # | Severity | Finding | Fix | Evidence |
|---|---|---|---|---|
| 1 | high | A data-plane host could forge or replay the probe marker (`FGPROBE:<table>:<priority>;`), make L2 fail for every drop rule, and push L1 findings over the quarantine threshold. Same-priority rules also collided. | The marker now carries a random per-cycle nonce and a probe index. A returning frame counts only while that exact cycle runs and only from that switch; unknown nonces are ignored; the per-cycle state is dropped after judging. | `tests/unit/test_phase5.py` (marker round trip, garbage ignored); live L2 tests |
| 2 | high | Quarantine could cut a port chosen by an intruder (a rule naming an uplink) or a legitimate port (derived from a deleted signed rule). | Only the rule found on the switch can name the port, never a missing signed rule; the port must be one where the learning switch has seen a host; at most 4 per switch; admin release is audited. | `test_quarantine_only_ever_targets_a_real_port_named_by_the_rule`; live quarantine test |
| 3 | medium | With dry run off, the default weights gave an L1-only finding 0.45, below the restore threshold, so automatic repair stopped. | A signed rule that fails verification never scores below the restore threshold. | `test_failed_signature_never_scores_below_restore...` |
| 4 | medium | `prototype.sh` (root) wrote logs and pid files under `/tmp`, which another local user can pre-create. | Logs and data live under `/run/flowguard`, created root-owned and checked before use. | script; `bin/flowguard status` |
| 5 | medium | `flowguard export` copied the whole core database (password hashes, sessions). | Export now writes only operational tables (alerts, incidents, events, snapshots, probes, scores); never users, sessions, the audit log, keys or the golden store. | `bin/flowguard export` |
| 6 | medium | A probe cycle that straddled a policy change could report a false failure; probes ignored quarantine rules; the L3 baseline learned from reconnect replays. | Cycles carry a rule-set generation and are discarded if it changed; probes plan from the desired rules including quarantine; replays do not teach the baseline. | live suite (26 tests) |
| 7 | low | Core accepted all-zero weights and partial `actions` that the engine rejects, so the dashboard could show a policy as live when it was not. Baseline file errors could stop the engine; baseline lists grew without bound; baseline path ignored the data dir and followed symlinks. | Same validation in the API; the response says if the hand-off to the engine failed; baseline validated, bounded (2000 samples), written without following symlinks, and relocated with the data dir. | `test_policies_the_engine_would_reject_are_rejected_by_the_api_too`; `test_baseline_is_bounded...` |
| 8 | low | Streamlit console put some API values into HTML unescaped. | All such values go through `html.escape`. | code |
| 9 | low | A policy rule at priority 65000 or above could collide with a quarantine rule. | Policy parsing rejects priorities of 65000 and above (reserved). | `test_policy_may_not_use_the_quarantine_priority_range` |

Also checked and found clean: the new endpoints are role-gated (viewer lists, admin releases and edits policy), CSRF applies to
cookie sessions, release input is validated and its file name is a random id, there is no raw-HTML sink in the React app.
Both new routes are in the role matrix test.

## Not checked, and residual risks
- Not checked: dependency vulnerabilities (`npm audit`, pip audit), the ZeroMQ endpoint's file permissions end to end,
  `stack.py` file modes inside the data directory, behaviour on real hardware.
- `bin/flowguard stop` and `prototype.sh` stop every `streamlit run` and `core.main` process on the machine as root. Acceptable
  for a single-user lab, not for a shared host.
- A host that can sniff a probe frame during its 0.4 s window could replay it with that cycle's nonce; the effect is limited
  to one cycle's L2 verdict.
- A forward rule's probe may be sent out of a host port; it carries nothing but the marker.
- The lab runs engine, core and keys on one host (documented in `docs/threat_model.md`).
- Quarantine means "drop everything arriving on one port"; there is no finer isolation. The policy action `quarantine_port`
  is off by default (dry run, and the default actions map to restore or alert).

Verify: `make test-security` (authentication, roles, CSRF, validation, crypto, Phase 5 logic) and `sudo make test-live`.

## Second pass: least privilege and the stress tests (2026-11-17)
Not an AI review: these are results of building and running the changes.
- **The engine and the core no longer run as root** (`scripts/service-users.sh`, `stack.py --drop-privileges`). `sudo make test-live`
  (`tests/integration/test_least_privilege_live.py`) proves it on the real lab: the processes run as `flowguard-engine` and
  `flowguard-core`; the HMAC key (mode 0600) is unreadable to the core, the user database (password hashes, sessions) is unreadable
  to the engine, the golden store is unreadable to the core; detection comes from monitor events, repair works, alerts reach the core,
  and the core's control files (key rotation, policy hand-off) reach the engine. This answers the residual risk "a bug in the core
  or the API can read the signing key".
- **Found by the stress tests and fixed:** the engine re-installed the signed policy on every connect before looking at the switch,
  silently overwriting rules changed while it was down (it now audits first); a crash on a connection that dies before the OpenFlow
  handshake; the change monitor not starting without root (silent fall back to the slow poll).
- **Still true:** the lab runs on one host, so root on that host defeats the product; Mininet and Open vSwitch themselves need root;
  the service accounts get a traverse-only ACL on the folders down to the checkout (reviewable with `getfacl`); `pkill` in the start
  and stop scripts is not scoped to one lab; there is still no authentication on the ZeroMQ socket beyond file permissions
  (group `flowguard`).
- Not re-reviewed by an AI after these changes: the new code was exercised by tests, not by a second reviewer.

