"""L2 data-plane canary probes: planning and judging (pure Python; the packet I/O lives in engine/app.py).

L1 trusts what the switch *reports* about its flow table. A switch that lies in its stats replies, or has a rule that is
present but not acting (shadowed, altered match, missing), passes L1 while forwarding wrongly. L2 checks behaviour: it
injects a small tagged packet into the pipeline (PacketOut to OFPP_TABLE) that the signed policy says must hit a given
rule, then checks that (a) that rule's packet counter rose by the number of probes sent and (b) a packet that should
have been dropped did not come back to the controller. Probes only exercise the lab's own signed rules. Every probe
carries a payload marker ``PROBE_MARK:<nonce>:<index>;`` with a random per-cycle nonce, and the controller counts a returning
probe only while that exact cycle is running, so a host cannot forge or replay results. A probe that a signed forward rule
sends out may reach a host port; it carries nothing but the marker.

Coverage: IPv4 and IPv6 TCP/UDP, ICMPv4 echo, ARP, rules bound to an ingress port (the probe is injected as if it
arrived there), exact MAC matches and masked addresses (``10.0.0.0/24``). Anything else (VLAN, MPLS, metadata, ...) is
skipped, never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .canonical import RuleSpec, _field_kind, _to_number

PROBE_MARK = b"FGPROBE"
PROBE_SRC_MAC = "02:f1:0e:00:00:01"  # default Ethernet addresses of a probe (locally administered)
PROBE_DST_MAC = "02:f1:0e:00:00:02"
SUPPORTED = {"in_port", "eth_type", "eth_src", "eth_dst", "ip_proto", "tcp_dst", "tcp_src", "udp_dst", "udp_src",
             "ipv4_src", "ipv4_dst", "ipv6_src", "ipv6_dst", "icmpv4_type", "icmpv4_code",
             "arp_op", "arp_spa", "arp_tpa", "arp_sha", "arp_tha"}
ETH_IPV4, ETH_ARP, ETH_IPV6 = 0x0800, 0x0806, 0x86DD
DEFAULTS: Dict[int, Dict[str, Any]] = {
    ETH_IPV4: {"eth_type": ETH_IPV4, "ip_proto": 6, "ipv4_src": "10.255.0.1", "ipv4_dst": "10.255.0.2", "tcp_src": 40000, "tcp_dst": 40001},
    ETH_IPV6: {"eth_type": ETH_IPV6, "ip_proto": 6, "ipv6_src": "fd00::1", "ipv6_dst": "fd00::2", "tcp_src": 40000, "tcp_dst": 40001},
    ETH_ARP: {"eth_type": ETH_ARP, "arp_op": 1, "arp_spa": "10.255.0.1", "arp_tpa": "10.255.0.2",
              "arp_sha": PROBE_SRC_MAC, "arp_tha": "00:00:00:00:00:00"},
}


def make_marker(nonce: str, idx: int) -> bytes:
    return PROBE_MARK + b":" + nonce.encode("ascii") + b":" + str(idx).encode("ascii") + b";"


def parse_marker(data: bytes) -> Optional[Tuple[str, int]]:
    """(nonce, probe index) of a canary frame, or None when the frame carries no well-formed marker."""
    at = data.find(PROBE_MARK + b":")
    if at < 0:
        return None
    try:
        nonce, idx = data[at + len(PROBE_MARK) + 1:].split(b";", 1)[0].split(b":")
        return nonce.decode("ascii"), int(idx)
    except (ValueError, UnicodeDecodeError):
        return None


@dataclass(frozen=True)
class ProbeSpec:
    table_id: int
    priority: int
    rule_key: str            # RuleSpec.match_key()
    expect: str              # drop | forward | goto
    fields: Mapping[str, Any]  # packet header fields the probe carries
    describe: str


def _num(name: str, v: Any) -> int:
    kind, _bits = _field_kind(name)
    return _to_number(kind, v, name)


def _value(v: Any) -> Any:
    """A canonical match value is a scalar or [value, mask]; a probe carries the value part."""
    return v[0] if isinstance(v, (list, tuple)) else v


def matches(rule_match: Mapping[str, Any], fields: Mapping[str, Any]) -> bool:
    """Match semantics for the supported fields (masks honoured); a field absent from the rule is a wildcard."""
    for k, rv in rule_match.items():
        fv = fields.get(k)
        if fv is None:
            return False
        try:
            if isinstance(rv, (list, tuple)):
                mask = _num(k, rv[1])
                if _num(k, fv) & mask != _num(k, rv[0]) & mask:
                    return False
            elif _num(k, fv) != _num(k, rv):
                return False
        except Exception:  # an unparseable value never matches
            return False
    return True


def expectation(spec: RuleSpec) -> str:
    ins = list(spec.instructions)
    if not ins:
        return "drop"
    types = {i.get("type") for i in ins}
    return "goto" if "goto_table" in types else "forward"


def synthesize(spec: RuleSpec) -> Optional[Dict[str, Any]]:
    """Header fields of a packet that matches ``spec``, or None if the match uses fields we cannot synthesize."""
    if any(k not in SUPPORTED for k in spec.match):
        return None
    eth_type = _value(spec.match.get("eth_type", ETH_IPV4))
    base = DEFAULTS.get(eth_type)
    if base is None:
        return None
    fields = dict(base)
    for k, v in spec.match.items():
        fields[k] = _value(v)
    if eth_type in (ETH_IPV4, ETH_IPV6):
        proto = fields["ip_proto"] if "ip_proto" in spec.match else None
        if proto is None:  # infer the L4 protocol from the L4 fields the rule names
            if any(k.startswith("udp_") for k in spec.match):
                proto = 17
            elif any(k.startswith("icmpv4_") for k in spec.match):
                proto = 1
            else:
                proto = 6
        fields["ip_proto"] = proto
        if proto == 17:
            fields.pop("tcp_src", None), fields.pop("tcp_dst", None)
            fields.setdefault("udp_src", 40000), fields.setdefault("udp_dst", 40001)
        elif proto == 1:
            fields.pop("tcp_src", None), fields.pop("tcp_dst", None)
            fields.setdefault("icmpv4_type", 8), fields.setdefault("icmpv4_code", 0)
        elif proto != 6:
            return None  # an IP protocol we cannot build a packet for
    return fields


def plan_probes(rules: Sequence[RuleSpec]) -> List[ProbeSpec]:
    """One probe per probe-able rule, skipping rules the policy itself shadows with a higher-priority rule."""
    out: List[ProbeSpec] = []
    for r in rules:
        fields = synthesize(r)
        if fields is None:
            continue
        winner = max((o for o in rules if o.table_id == r.table_id and matches(o.match, fields)), key=lambda o: o.priority, default=None)
        if winner is None or winner.key() != r.key():
            continue  # a legitimately higher-priority signed rule takes this packet; it gets its own probe
        out.append(ProbeSpec(r.table_id, r.priority, r.match_key(), expectation(r), fields, r.describe() if hasattr(r, "describe") else r.match_key()))
    return out


@dataclass(frozen=True)
class Verdict:
    status: str   # pass | fail | inconclusive
    reason: str
    l2: float     # 0 pass, 1 fail: the L2 input to the risk engine


def judge(spec: ProbeSpec, sent: int, before: Optional[int], after: Optional[int], leaked: int) -> Verdict:
    if before is None or after is None:
        return Verdict("inconclusive", "the signed rule is not in the switch's flow stats, so no counter could be compared", 1.0)
    delta = after - before
    if delta < sent:
        return Verdict("fail", f"probe did not hit the signed rule (counter rose {delta} of {sent}): forwarding differs from the signed policy", 1.0)
    if spec.expect == "drop" and leaked > 0:
        return Verdict("fail", f"{leaked} probe packet(s) that must be dropped reached the controller", 1.0)
    return Verdict("pass", f"probe hit the signed rule ({delta} of {sent}) and behaved as signed ({spec.expect})", 0.0)
