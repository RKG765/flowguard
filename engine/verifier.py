"""L1 verifier: compares what a switch holds with the signed golden rules (pure Python).

Classes of finding for a critical table:
  ok       observed rule equals the golden rule and carries its cookie
  missing  a golden rule is absent from the switch
  altered  same (table, priority, match) as a golden rule, but different instructions or cookie
  shadow   a rule that is not golden and overlaps a golden rule at equal or higher priority (takes its traffic);
           golden table-miss rules (empty match) are ignored here because they overlap everything
  forged   any other rule that is not golden
For shadow and forged rules ``signature_valid`` says whether the cookie nevertheless verifies (a replayed or
stale signed rule); the response is the same. ``Pending`` tracks the engine's own FlowMods so that they are
attributed instead of alerted on (the grace window).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .canonical import RuleSpec, dpid_hex, matches_overlap
from .crypto import Signer
from .store import GoldenRule

OK, MISSING, ALTERED, SHADOW, FORGED = "ok", "missing", "altered", "shadow", "forged"
BAD_KINDS = (MISSING, ALTERED, SHADOW, FORGED)


@dataclass(frozen=True)
class ObservedRule:
    spec: RuleSpec
    cookie: int


@dataclass(frozen=True)
class Finding:
    kind: str
    dpid: str
    spec: RuleSpec  # the rule slot the finding is about (observed spec, or golden spec for `missing`)
    observed: Optional[ObservedRule] = None
    golden: Optional[GoldenRule] = None
    signature_valid: Optional[bool] = None
    reasons: Tuple[str, ...] = ()
    shadows: Tuple[str, ...] = ()  # descriptions of golden rules this rule takes traffic from

    def key(self) -> Tuple[str, str, int, int, str, int]:
        """Stable identity used for de-duplication: (dpid, kind, table, priority, match, observed cookie)."""
        return (self.dpid, self.kind, self.spec.table_id, self.spec.priority, self.spec.match_key(),
                self.observed.cookie if self.observed else 0)


Slot = Tuple[int, int, str]  # (table_id, priority, canonical match): the identity of a rule position


def classify(dpid: object, observed: Sequence[ObservedRule], golden: Sequence[GoldenRule], signer: Signer,
             now: Optional[float] = None, skip_slots: Optional[Set[Slot]] = None) -> List[Finding]:
    """Classify one switch's critical table(s). ``observed`` and ``golden`` must cover the same tables.

    Rule slots in ``skip_slots`` (the engine's own in-flight FlowMods) are not judged yet. Skipping by SLOT, not by
    cookie, matters: an attacker who copies a golden cookie onto a different rule must not hide inside the grace window.
    Returns only bad findings, ordered deterministically.
    """
    ts = time.time() if now is None else now
    skip = skip_slots or set()
    dp = dpid_hex(dpid)
    gold_by_key = {g.spec.key(): g for g in golden}
    obs_by_key = {o.spec.key(): o for o in observed}
    findings: List[Finding] = []

    for key, g in gold_by_key.items():
        o = obs_by_key.get(key)
        if key in skip:
            continue
        if o is None:
            findings.append(Finding(MISSING, dp, g.spec, None, g, None, ("rule_absent",)))
            continue
        reasons = []
        if o.spec.content_key() != g.spec.content_key():
            reasons.append("instructions_differ")
        if o.cookie != g.cookie:
            reasons.append("cookie_differs")
        if reasons:
            sig = signer.verify(dpid, o.spec, o.cookie, ts).valid
            findings.append(Finding(ALTERED, dp, o.spec, o, g, sig, tuple(reasons)))

    for key, o in obs_by_key.items():
        if key in gold_by_key or key in skip:
            continue
        # A table-miss golden rule (empty match) overlaps everything, so it is excluded: otherwise every unknown
        # rule would be labelled `shadow` and the label would carry no information.
        shadowed = tuple(sorted(g.spec.describe() for g in golden
                                if g.spec.match and g.spec.table_id == o.spec.table_id
                                and o.spec.priority >= g.spec.priority and matches_overlap(o.spec.match, g.spec.match)))
        sig = signer.verify(dpid, o.spec, o.cookie, ts).valid
        kind = SHADOW if shadowed else FORGED
        findings.append(Finding(kind, dp, o.spec, o, None, sig, ("not_in_golden_store",), shadowed))

    findings.sort(key=lambda f: (f.spec.table_id, -f.spec.priority, f.spec.match_key(), f.kind))
    return findings


def explain(f: Finding) -> str:
    """One plain-language sentence (no OpenFlow knowledge needed) for alerts."""
    where = f.spec.describe()
    if f.kind == MISSING:
        return f"A rule the controller installed is gone from the switch ({where}). It was removed outside the controller."
    if f.kind == ALTERED:
        return f"A signed rule was changed on the switch ({where}). What it does no longer matches what the controller installed."
    if f.kind == SHADOW:
        return (f"An unknown rule ({where}) sits above a protected rule and takes over its traffic. "
                f"{'It carries a valid signature (a replayed or stale rule). ' if f.signature_valid else 'It is not signed by the controller. '}")
    return f"An unknown rule that the controller did not install appeared on the switch ({where})."


# ---- attribution of the engine's own changes ----------------------------------------------------------------
@dataclass
class _Expect:
    dpid: str
    table_id: int
    cookie: int
    events: Tuple[str, ...]
    expires: float
    consumed: bool = False
    tag: Optional[object] = None  # caller's label, e.g. the rule slot a restore is for
    slot: Optional[Slot] = None   # the rule position this change touches (exempt from judgement while in flight)


class Pending:
    """Tracks FlowMods the engine itself sent, so their monitor events are attributed and their rules skipped
    while the change is in flight. Entries expire after ``grace_seconds``."""

    def __init__(self, grace_seconds: float = 0.5) -> None:
        self.grace = grace_seconds
        self._items: List[_Expect] = []

    def expect(self, dpid: object, table_id: int, cookie: int, events: Iterable[str], now: Optional[float] = None,
               tag: Optional[object] = None, slot: Optional[Slot] = None) -> None:
        ts = time.time() if now is None else now
        self._items.append(_Expect(dpid_hex(dpid), table_id, cookie, tuple(events), ts + self.grace, tag=tag, slot=slot))

    def _prune(self, now: float) -> None:
        self._items = [i for i in self._items if i.expires >= now]

    def match(self, dpid: object, table_id: int, event: str, cookie: int, now: Optional[float] = None) -> Optional[_Expect]:
        """The live expectation that explains this monitor event (marked consumed), or None."""
        ts = time.time() if now is None else now
        self._prune(ts)
        dp = dpid_hex(dpid)
        for i in self._items:
            if i.dpid == dp and i.table_id == table_id and i.cookie == cookie and event in i.events and not i.consumed:
                i.consumed = True
                return i
        return None

    def attribute(self, dpid: object, table_id: int, event: str, cookie: int, now: Optional[float] = None) -> bool:
        """True if a live expectation explains this monitor event (and mark it consumed)."""
        return self.match(dpid, table_id, event, cookie, now) is not None

    def live_slots(self, dpid: object, now: Optional[float] = None) -> Set[Slot]:
        """Rule slots with an engine-made change still in flight."""
        ts = time.time() if now is None else now
        self._prune(ts)
        dp = dpid_hex(dpid)
        return {i.slot for i in self._items if i.dpid == dp and i.slot is not None}

    def live_cookies(self, dpid: object, now: Optional[float] = None) -> Set[int]:
        ts = time.time() if now is None else now
        self._prune(ts)
        dp = dpid_hex(dpid)
        return {i.cookie for i in self._items if i.dpid == dp}

    def __len__(self) -> int:
        return len(self._items)


# ---- alert de-duplication -----------------------------------------------------------------------------------
class Deduper:
    """Suppress repeats of the same finding for ``window_seconds`` (a persistent finding re-alerts after that)."""

    def __init__(self, window_seconds: float = 30.0) -> None:
        self.window = window_seconds
        self._seen: Dict[tuple, float] = {}

    def should_alert(self, key: tuple, now: Optional[float] = None) -> bool:
        ts = time.time() if now is None else now
        last = self._seen.get(key)
        if last is not None and ts - last < self.window:
            return False
        self._seen[key] = ts
        if len(self._seen) > 4096:  # bound memory
            cutoff = ts - self.window
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
        return True
