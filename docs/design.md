# Design notes

Phase 0 only. The detailed design grows per phase; the decisions behind it are in `DECISIONS.md`.

## L1 data path
1. All controller installs go through `install_signed_rule()` (Phase 1): canonicalize -> HMAC tag -> cookie -> golden store -> FlowMod.
2. A monitor session (ADR-004) reports that a critical table changed; the verifier fetches the table with a targeted stats request and classifies every rule: `ok`, `forged`, `altered`, `shadow`, `missing`. A pending set with a grace window absorbs the race between the controller's own installs and the monitor events.
3. The responder restores the golden rule (rate limited per switch) and never deletes on an unverified mismatch.

## Canonical form (Phase 1)
Bytes over (dpid, epoch16, table_id, priority, sorted normalized match fields, normalized instructions). Excluded: counters, durations, timeouts, flags, cookie.

## Table layout (ADR-006)
Table 0 security/ACL (miss -> goto 1); table 1 learning switch (miss -> controller).

## Alert spool (ADR-009)
Append-only JSONL, fsync per alert, 10 MiB x 5 files, overflow counted and surfaced.
