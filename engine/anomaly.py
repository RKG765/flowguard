"""L3 anomaly scorer: a robust statistical baseline over rule-change events (pure Python, no numpy).

It learns what *normal* rule churn looks like in the lab (how often rules change, at which priorities, which action
classes) from legitimate, signed changes, then scores each new change event in [0, 1]. This is a baseline model, not
a neural network: each feature gives a robust z-score (median and MAD), squashed to [0, 1], and the features are
combined as a noisy-OR so one strongly unusual feature is enough. It exists to catch what L1 cannot: a rule that is
correctly signed but behaves unlike anything seen before (for example a signed drop at a priority far above the rest).
Features are explainable, so every score carries the reasons behind it.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter, deque
from typing import Any, Deque, Dict, Iterable, List, Mapping, Optional, Tuple

WINDOW_S = 60.0
MIN_SAMPLES = 8  # below this the baseline is too thin to judge; scores stay low and say so
MAX_SAMPLES = 2000  # the baseline is a sliding window, so memory and scoring time stay bounded


def action_class(instructions: Optional[Iterable[Mapping[str, Any]]]) -> str:
    ins = list(instructions or [])
    if not ins:
        return "drop"
    types = {i.get("type") for i in ins}
    if "goto_table" in types:
        return "goto"
    if "apply_actions" in types:
        return "forward"
    return "other"


def _median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def robust_z(x: float, xs: List[float]) -> float:
    """z-score from median and MAD (1.4826 x MAD ~ sigma for normal data). A flat baseline uses a floor of 1."""
    med = _median(xs)
    mad = _median([abs(v - med) for v in xs])
    return (x - med) / max(1.4826 * mad, 1.0)


def squash(z: float, knee: float = 3.0) -> float:
    """0 for z <= 0, ~0.5 at z == knee, approaching 1 beyond it."""
    return 0.0 if z <= 0 else 1.0 - math.exp(-math.log(2) * z / knee)


class AnomalyScorer:
    def __init__(self) -> None:
        self.rates: List[float] = []        # changes per 60 s window, one sample per learned event
        self.priorities: List[float] = []
        self.classes: Counter = Counter()   # action class -> count
        self.recent: Dict[str, Deque[float]] = {}

    # ---- learning ------------------------------------------------------------------------------------------------
    def _rate(self, dpid: str, t: float) -> int:
        q = self.recent.setdefault(dpid, deque())
        q.append(t)
        while q and t - q[0] > WINDOW_S:
            q.popleft()
        return len(q)

    def learn(self, ev: Mapping[str, Any]) -> None:
        """Add one legitimate change to the baseline."""
        self.rates.append(float(self._rate(str(ev.get("dpid")), float(ev["t"]))))
        self.priorities.append(float(ev.get("priority", 0)))
        self.classes[ev.get("action_class", "other")] += 1
        for xs in (self.rates, self.priorities):
            if len(xs) > MAX_SAMPLES:
                del xs[: len(xs) - MAX_SAMPLES]

    @property
    def ready(self) -> bool:
        return len(self.priorities) >= MIN_SAMPLES

    # ---- scoring -------------------------------------------------------------------------------------------------
    def score(self, ev: Mapping[str, Any]) -> Tuple[float, List[str]]:
        """Return (score in [0, 1], reasons). Does not change the baseline; call learn() for legitimate events."""
        reasons: List[str] = []
        parts: List[float] = []
        q = self.recent.get(str(ev.get("dpid")), deque())
        t = float(ev["t"])
        rate = sum(1 for x in q if t - x <= WINDOW_S) + 1
        if not ev.get("signed", True):
            parts.append(0.6)
            reasons.append("the rule is not signed by the controller")
        if not self.ready:
            return (max(parts) if parts else 0.0), reasons + [f"baseline still learning ({len(self.priorities)}/{MIN_SAMPLES} samples)"]
        rz = squash(robust_z(float(rate), self.rates))
        if rz > 0.2:
            parts.append(rz)
            reasons.append(f"{rate} changes in the last minute is unusual for this lab")
        pz = squash(robust_z(float(ev.get("priority", 0)), self.priorities))
        if pz > 0.2:
            parts.append(pz)
            reasons.append(f"priority {ev.get('priority')} is far from the usual priorities")
        cls = ev.get("action_class", "other")
        total = sum(self.classes.values())
        share = self.classes.get(cls, 0) / total if total else 0.0
        if share < 0.1:
            c = 0.5 * (1 - share / 0.1) + 0.2
            parts.append(c)
            reasons.append(f"'{cls}' actions are rare in normal churn ({share:.0%})")
        score = 1.0
        for p in parts:
            score *= 1.0 - min(1.0, p)
        return round(1.0 - score, 4), reasons

    # ---- persistence ----------------------------------------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({"rates": self.rates[-2000:], "priorities": self.priorities[-2000:], "classes": dict(self.classes)})

    @staticmethod
    def from_json(text: str) -> "AnomalyScorer":
        d = json.loads(text)
        if not (isinstance(d, dict) and isinstance(d.get("rates"), list) and isinstance(d.get("priorities"), list) and isinstance(d.get("classes"), dict)):
            raise ValueError("not a baseline file")
        s = AnomalyScorer()
        s.rates, s.priorities, s.classes = list(map(float, d["rates"])), list(map(float, d["priorities"])), Counter(d["classes"])
        return s

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)  # never follow a planted symlink
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())
        os.replace(tmp, path)

    @staticmethod
    def load(path: str) -> "AnomalyScorer":
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return AnomalyScorer.from_json(fh.read())
        except (OSError, ValueError, KeyError, TypeError):
            return AnomalyScorer()
