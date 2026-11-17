"""Risk engine: fuses the three detection layers under the policy document (pure Python).

L1 = signed-rule verification (0 or 1), L2 = data-plane canary probe (0 = forwards as signed, 1 = does not),
L3 = anomaly score in [0, 1]. The fused score is the weighted mean of the three, so a layer the policy weights at 0 is
ignored. Two safety rules are fixed in code, not in the policy:

* A signed rule that fails verification (L1 = 1) is cryptographic evidence: its score never falls below the restore
  threshold, so turning dry run off cannot silently stop the repair of a forged or altered rule.
* ML alone never repairs anything: with no L1 or L2 evidence, the action is capped at ``alert_only``.
* ``dry_run`` records what would happen (``action``) but makes the engine do nothing (``effective_action == "none"``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

SEVERITIES = ("low", "medium", "high", "critical")
ACTIONS = ("restore_and_alert", "quarantine_port", "alert_only", "none")
DESTRUCTIVE = ("restore_and_alert", "quarantine_port")

DEFAULT_DOC: Dict[str, Any] = {
    "dry_run": True,
    "weights": {"l1": 1.0, "l2": 0.8, "l3": 0.4},
    "thresholds": {"alert": 0.3, "restore": 0.5, "quarantine": 0.8},
    "actions": {"critical": "restore_and_alert", "high": "restore_and_alert", "medium": "alert_only", "low": "alert_only"},
}


@dataclass(frozen=True)
class RiskPolicy:
    dry_run: bool
    weights: Tuple[float, float, float]
    thresholds: Tuple[float, float, float]  # alert, restore, quarantine
    actions: Tuple[Tuple[str, str], ...]

    @staticmethod
    def from_doc(doc: Mapping[str, Any]) -> "RiskPolicy":
        d = {**DEFAULT_DOC, **{k: v for k, v in doc.items() if k in DEFAULT_DOC}}
        w, t = d["weights"], d["thresholds"]
        weights = (float(w["l1"]), float(w["l2"]), float(w["l3"]))
        thresholds = (float(t["alert"]), float(t["restore"]), float(t["quarantine"]))
        if min(weights) < 0 or sum(weights) <= 0:
            raise ValueError("weights must be non-negative and not all zero")
        if not thresholds[0] <= thresholds[1] <= thresholds[2]:
            raise ValueError("thresholds must satisfy alert <= restore <= quarantine")
        actions = d["actions"]
        for sev in SEVERITIES:
            if actions.get(sev) not in ACTIONS:
                raise ValueError(f"unknown action for severity {sev}: {actions.get(sev)!r}")
        return RiskPolicy(bool(d["dry_run"]), weights, thresholds, tuple(sorted(actions.items())))


@dataclass(frozen=True)
class Decision:
    score: float
    severity: str
    action: str            # what the policy asks for
    effective_action: str  # what the engine will actually do (dry run and the ML-only cap applied)
    dry_run: bool
    parts: Tuple[float, float, float]
    capped: bool           # True when the ML-only safety cap changed the action

    def to_dict(self) -> Dict[str, Any]:
        return {"score": round(self.score, 4), "severity": self.severity, "action": self.action,
                "effective_action": self.effective_action, "dry_run": self.dry_run, "capped": self.capped,
                "l1": self.parts[0], "l2": self.parts[1], "l3": round(self.parts[2], 4)}


def quarantine_port(match: Mapping[str, Any]) -> "int | None":
    """The ingress port a rule is bound to (its in_port match), or None when the rule says nothing about a port.
    Only a real, non-reserved port is ever returned: quarantine never guesses which port to cut."""
    p = match.get("in_port") if match else None
    return p if isinstance(p, int) and 0 < p < 0xFFFFFF00 else None


def severity_for(score: float, policy: RiskPolicy) -> str:
    alert, restore, quarantine = policy.thresholds
    if score >= quarantine:
        return "critical"
    if score >= restore:
        return "high"
    if score >= alert:
        return "medium"
    return "low"


def fuse(policy: RiskPolicy, l1: float, l2: float, l3: float) -> Decision:
    l1, l2, l3 = (min(1.0, max(0.0, float(x))) for x in (l1, l2, l3))
    w1, w2, w3 = policy.weights
    score = (w1 * l1 + w2 * l2 + w3 * l3) / (w1 + w2 + w3)
    if l1 >= 1.0:
        score = max(score, policy.thresholds[1])
    sev = severity_for(score, policy)
    action = dict(policy.actions)[sev]
    capped = False
    if action in DESTRUCTIVE and l1 == 0 and l2 == 0:  # ML alone never repairs
        action, capped = "alert_only", True
    if score < policy.thresholds[0]:
        action = "none"
    effective = "none" if policy.dry_run else action
    return Decision(score, sev, action, effective, policy.dry_run, (l1, l2, l3), capped)
