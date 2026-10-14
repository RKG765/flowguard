"""Policy file: the rules the controller wants installed (and signed) on every switch (pure Python).

YAML or JSON::

    rules:
      - {table: 0, priority: 100, match: {eth_type: 0x0800, ip_proto: 6, tcp_dst: 23}, instructions: []}
      - {table: 0, priority: 0, match: {}, instructions: [{type: goto_table, table_id: 1}]}

An empty instruction list is a drop. Optional ``dpids: ["0000000000000001"]`` on a rule limits it to those switches.
Changing the file is "legitimate churn": the engine applies the difference with signed installs and signed
retirements, which must not raise alerts.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .canonical import CanonicalError, RuleSpec, dpid_hex


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class PolicyRule:
    spec: RuleSpec
    dpids: Optional[Tuple[str, ...]]  # None = every switch

    def applies_to(self, dpid: object) -> bool:
        return self.dpids is None or dpid_hex(dpid) in self.dpids


def parse_policy(data: Any) -> List[PolicyRule]:
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise PolicyError("policy must be a mapping with a 'rules' list")
    out: List[PolicyRule] = []
    seen: Set[Tuple[Tuple[int, int, str], Optional[Tuple[str, ...]]]] = set()
    for idx, raw in enumerate(data["rules"]):
        if not isinstance(raw, dict):
            raise PolicyError(f"rule #{idx}: must be a mapping")
        try:
            spec = RuleSpec.from_dict(raw)
            dpids = tuple(sorted(dpid_hex(d) for d in raw["dpids"])) if raw.get("dpids") else None
        except CanonicalError as exc:
            raise PolicyError(f"rule #{idx}: {exc}") from exc
        ident = (spec.key(), dpids)
        if ident in seen:
            raise PolicyError(f"rule #{idx}: duplicate of an earlier rule ({spec.describe()})")
        seen.add(ident)
        out.append(PolicyRule(spec, dpids))
    return out


def load_policy(path: str) -> List[PolicyRule]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    try:
        if path.endswith(".json"):
            data = json.loads(text)
        else:
            import yaml  # PyYAML is in both venvs
            data = yaml.safe_load(text)
    except Exception as exc:  # malformed YAML/JSON of any kind
        raise PolicyError(f"cannot parse policy {path}: {exc}") from exc
    return parse_policy(data)


def rules_for(policy: Iterable[PolicyRule], dpid: object) -> List[RuleSpec]:
    return [r.spec for r in policy if r.applies_to(dpid)]


def diff(old: Iterable[RuleSpec], new: Iterable[RuleSpec]) -> Tuple[List[RuleSpec], List[RuleSpec]]:
    """Return (to_install, to_retire). A rule whose key exists in both but whose content changed is re-installed."""
    old_by_key: Dict[Tuple[int, int, str], RuleSpec] = {s.key(): s for s in old}
    new_by_key: Dict[Tuple[int, int, str], RuleSpec] = {s.key(): s for s in new}
    install = [s for k, s in new_by_key.items() if k not in old_by_key or old_by_key[k].content_key() != s.content_key()]
    retire = [s for k, s in old_by_key.items() if k not in new_by_key]
    return install, retire


def file_signature(path: str) -> Optional[Tuple[float, int]]:
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None
