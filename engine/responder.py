"""Responder policy: turn findings into planned actions (pure Python; the Ryu app executes them).

Safety rules:
  * restore = re-install the golden rule with an OFPFC_ADD (atomically replaces an altered rule, re-creates a missing one)
  * delete  = strict delete of a rule that is NOT in the golden store, only when it was classified forged/shadow
  * never delete on a mismatch we could not verify (unparseable rules never reach this module: they alert only)
  * rate limited per switch (sliding 60 s window) so an attacker cannot make the engine fight in a loop
  * `alert_only` mode (dry run) plans nothing destructive
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

from .verifier import ALTERED, FORGED, MISSING, SHADOW, Finding

RESTORE, DELETE, NONE = "restore", "delete", "none"
MODE_RESTORE, MODE_ALERT_ONLY = "restore", "alert_only"


@dataclass(frozen=True)
class PlannedAction:
    op: str  # restore | delete | none
    finding: Finding
    reason: str  # why op is `none` (alert_only | rate_limited), or the rationale for a real action


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, dpid: str, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        q = self._events[dpid]
        while q and ts - q[0] >= 60.0:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(ts)
        return True


class Responder:
    def __init__(self, mode: str = MODE_RESTORE, per_minute: int = 30) -> None:
        if mode not in (MODE_RESTORE, MODE_ALERT_ONLY):
            raise ValueError(f"unknown response mode {mode!r}")
        self.mode = mode
        self.limiter = RateLimiter(per_minute)

    def plan(self, findings: List[Finding], now: Optional[float] = None) -> List[PlannedAction]:
        out: List[PlannedAction] = []
        for f in findings:
            op = RESTORE if f.kind in (MISSING, ALTERED) else DELETE if f.kind in (FORGED, SHADOW) else NONE
            if op == NONE:
                continue
            if self.mode == MODE_ALERT_ONLY:
                out.append(PlannedAction(NONE, f, "alert_only"))
            elif not self.limiter.allow(f.dpid, now):
                out.append(PlannedAction(NONE, f, "rate_limited"))
            else:
                out.append(PlannedAction(op, f, "golden_rule_restore" if op == RESTORE else "unsigned_rule_removal"))
        return out
