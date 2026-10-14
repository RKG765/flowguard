"""Deterministic canonical form of an OpenFlow rule (pure Python, no Ryu import).

A rule is identified and signed by (dpid, epoch, table_id, priority, normalized match, normalized
instructions). Excluded on purpose: counters, durations, idle/hard timeouts, flags and the cookie itself.

The same logical rule always yields the same bytes, whatever order the match fields or write-actions were
given in, whatever spelling of MAC/IP/port numbers was used, and whether it came from a policy file or from
a switch stats reply (see ``ryu_codec``).
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

CANONICAL_VERSION = b"FG1"

MAC_FIELDS = {"eth_src", "eth_dst", "arp_sha", "arp_tha", "ipv6_nd_sll", "ipv6_nd_tll"}
IPV4_FIELDS = {"ipv4_src", "ipv4_dst", "arp_spa", "arp_tpa"}
IPV6_FIELDS = {"ipv6_src", "ipv6_dst", "ipv6_nd_target"}
# bit widths of integer match fields (used to drop all-ones masks); unknown fields keep their mask as given
FIELD_BITS = {
    "in_port": 32, "in_phy_port": 32, "metadata": 64, "eth_type": 16, "vlan_vid": 13, "vlan_pcp": 3,
    "ip_dscp": 6, "ip_ecn": 2, "ip_proto": 8, "tcp_src": 16, "tcp_dst": 16, "udp_src": 16, "udp_dst": 16,
    "sctp_src": 16, "sctp_dst": 16, "icmpv4_type": 8, "icmpv4_code": 8, "icmpv6_type": 8, "icmpv6_code": 8,
    "arp_op": 16, "mpls_label": 20, "tunnel_id": 64, "ipv6_flabel": 20,
}
MAC_BITS, IPV4_BITS, IPV6_BITS = 48, 32, 128

PORT_NAMES = {
    "IN_PORT": 0xFFFFFFF8, "TABLE": 0xFFFFFFF9, "NORMAL": 0xFFFFFFFA, "FLOOD": 0xFFFFFFFB, "ALL": 0xFFFFFFFC,
    "CONTROLLER": 0xFFFFFFFD, "LOCAL": 0xFFFFFFFE, "ANY": 0xFFFFFFFF,
}
OFPP_CONTROLLER = PORT_NAMES["CONTROLLER"]
DEFAULT_CONTROLLER_MAX_LEN = 0xFFFF  # OFPCML_NO_BUFFER

# OpenFlow 1.3 executes instructions in this order regardless of the order they are listed in
INSTRUCTION_RANK = {"meter": 0, "apply_actions": 1, "clear_actions": 2, "write_actions": 3, "write_metadata": 4,
                    "goto_table": 5}
_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}([:-][0-9a-fA-F]{2}){5}$")


class CanonicalError(ValueError):
    """The rule cannot be normalized (unknown shape, bad value). Callers must NOT act destructively on it."""


# ---- field values ------------------------------------------------------------------------------------------
def _to_int(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise CanonicalError(f"{what}: boolean is not a valid number")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise CanonicalError(f"{what}: not a number: {value!r}") from exc
    raise CanonicalError(f"{what}: unsupported type {type(value).__name__}")


def _mac_to_int(value: Any, what: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and _MAC_RE.match(value):
        return int(value.replace("-", ":").replace(":", ""), 16)
    raise CanonicalError(f"{what}: bad MAC {value!r}")


def _int_to_mac(n: int) -> str:
    return ":".join(f"{(n >> s) & 0xFF:02x}" for s in range(40, -8, -8))


def _ip_to_int(value: Any, version: int, what: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(ipaddress.ip_address(value))  # type: ignore[arg-type]
    except ValueError as exc:
        raise CanonicalError(f"{what}: bad IPv{version} address {value!r}") from exc


def _field_kind(name: str) -> Tuple[str, int]:
    """Return (kind, bits). kind in mac | ipv4 | ipv6 | int | opaque."""
    if name in MAC_FIELDS:
        return "mac", MAC_BITS
    if name in IPV4_FIELDS:
        return "ipv4", IPV4_BITS
    if name in IPV6_FIELDS:
        return "ipv6", IPV6_BITS
    if name in FIELD_BITS:
        return "int", FIELD_BITS[name]
    return "int", 0  # unknown integer field: bits unknown, so all-ones masks are not dropped


def _to_number(kind: str, value: Any, what: str) -> int:
    if kind == "mac":
        return _mac_to_int(value, what)
    if kind == "ipv4":
        return _ip_to_int(value, 4, what)
    if kind == "ipv6":
        return _ip_to_int(value, 6, what)
    return _to_int(value, what)


def _from_number(kind: str, n: int) -> Any:
    if kind == "mac":
        return _int_to_mac(n)
    if kind == "ipv4":
        return str(ipaddress.IPv4Address(n))
    if kind == "ipv6":
        return str(ipaddress.IPv6Address(n))
    return n


def _split_masked(kind: str, bits: int, value: Any) -> Tuple[Any, Optional[Any]]:
    """Accept scalar, [value, mask], (value, mask) or 'a.b.c.d/len|mask' strings."""
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise CanonicalError(f"masked value must have 2 items: {value!r}")
        return value[0], value[1]
    if isinstance(value, str) and "/" in value and kind in ("ipv4", "ipv6"):
        addr, mask = value.split("/", 1)
        if mask.isdigit():
            plen = int(mask)
            if not 0 <= plen <= bits:
                raise CanonicalError(f"bad prefix length in {value!r}")
            return addr, _from_number(kind, ((1 << bits) - 1) ^ ((1 << (bits - plen)) - 1))
        return addr, mask
    return value, None


def normalize_field(name: str, value: Any) -> Any:
    """Normalize one match/set-field value to int, canonical string, or [value, mask] (masked)."""
    kind, bits = _field_kind(name)
    raw, raw_mask = _split_masked(kind, bits, value)
    num = _to_number(kind, raw, name)
    if raw_mask is None:
        return _from_number(kind, num)
    mask = _to_number(kind, raw_mask, f"{name} mask")
    if bits and mask == (1 << bits) - 1:
        return _from_number(kind, num)  # all-ones mask == exact match
    return [_from_number(kind, num & mask), _from_number(kind, mask)]


def field_value_and_mask(name: str, normalized: Any) -> Tuple[int, Optional[int]]:
    """Inverse of ``normalize_field`` used for overlap analysis: returns (value, mask) as integers."""
    kind, _ = _field_kind(name)
    if isinstance(normalized, list):
        return _to_number(kind, normalized[0], name), _to_number(kind, normalized[1], name)
    return _to_number(kind, normalized, name), None


def normalize_match(match: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(match, Mapping):
        raise CanonicalError("match must be a mapping")
    out = {str(k): normalize_field(str(k), v) for k, v in match.items()}
    return {k: out[k] for k in sorted(out)}


def matches_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """True when some packet can match both (already-normalized) matches. Fields only one side has are wildcards."""
    for name in set(a) & set(b):
        try:
            va, ma = field_value_and_mask(name, a[name])
            vb, mb = field_value_and_mask(name, b[name])
        except CanonicalError:
            return True  # cannot analyse: assume overlap (conservative)
        common = (-1 if ma is None else ma) & (-1 if mb is None else mb)
        if (va ^ vb) & common:
            return False
    return True


# ---- actions and instructions ------------------------------------------------------------------------------
def _port_number(port: Any) -> int:
    if isinstance(port, str) and port.upper() in PORT_NAMES:
        return PORT_NAMES[port.upper()]
    return _to_int(port, "output port")


def normalize_action(action: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(action, Mapping) or "type" not in action:
        raise CanonicalError(f"action needs a 'type': {action!r}")
    t = str(action["type"])
    if t == "output":
        port = _port_number(action.get("port"))
        out: Dict[str, Any] = {"type": "output", "port": port}
        if port == OFPP_CONTROLLER:
            out["max_len"] = _to_int(action.get("max_len", DEFAULT_CONTROLLER_MAX_LEN), "max_len")
        return out  # max_len is meaningless for other ports (OVS reports 65509 there), so it is dropped
    if t == "set_field":
        name = str(action["field"])
        return {"type": "set_field", "field": name, "value": normalize_field(name, action["value"])}
    if t == "group":
        return {"type": "group", "group_id": _to_int(action["group_id"], "group_id")}
    if t == "set_queue":
        return {"type": "set_queue", "queue_id": _to_int(action["queue_id"], "queue_id")}
    if t in ("push_vlan", "push_mpls", "push_pbb"):
        return {"type": t, "ethertype": _to_int(action["ethertype"], "ethertype")}
    if t in ("pop_vlan", "dec_nw_ttl"):
        return {"type": t}
    if t == "raw":  # codec fallback for actions we do not model; compared verbatim
        return {"type": "raw", "class": str(action["class"]), "params": json.loads(json.dumps(action["params"], sort_keys=True))}
    raise CanonicalError(f"unsupported action type {t!r}")


def _action_key(action: Mapping[str, Any]) -> str:
    return json.dumps(action, sort_keys=True, separators=(",", ":"))


def normalize_instruction(ins: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(ins, Mapping) or "type" not in ins:
        raise CanonicalError(f"instruction needs a 'type': {ins!r}")
    t = str(ins["type"])
    if t == "goto_table":
        return {"type": t, "table_id": _to_int(ins["table_id"], "table_id")}
    if t in ("apply_actions", "write_actions"):
        actions = [normalize_action(a) for a in ins.get("actions", [])]
        if t == "write_actions":  # an action *set*: order is irrelevant
            actions.sort(key=_action_key)
        return {"type": t, "actions": actions}
    if t == "clear_actions":
        return {"type": t}
    if t == "write_metadata":
        return {"type": t, "metadata": _to_int(ins["metadata"], "metadata"), "mask": _to_int(ins.get("mask", 0xFFFFFFFFFFFFFFFF), "mask")}
    if t == "meter":
        return {"type": t, "meter_id": _to_int(ins["meter_id"], "meter_id")}
    raise CanonicalError(f"unsupported instruction type {t!r}")


def normalize_instructions(instructions: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out = [normalize_instruction(i) for i in instructions]
    out.sort(key=lambda i: INSTRUCTION_RANK.get(i["type"], 99))  # stable: keeps order among equal ranks
    return out


# ---- rule ---------------------------------------------------------------------------------------------------
def normalize_dpid(dpid: Any) -> int:
    """Accept 1, '1', '0x1' or the 16-hex-digit form used by Mininet/OVS ('0000000000000001')."""
    if isinstance(dpid, bool):
        raise CanonicalError("bad dpid")
    if isinstance(dpid, int):
        n = dpid
    elif isinstance(dpid, str):
        s = dpid.strip().lower()
        try:
            n = int(s, 16) if (len(s) == 16 or s.startswith("0x")) else int(s, 10)
        except ValueError as exc:
            raise CanonicalError(f"bad dpid {dpid!r}") from exc
    else:
        raise CanonicalError(f"bad dpid {dpid!r}")
    if not 0 <= n < 1 << 64:
        raise CanonicalError(f"dpid out of range: {n}")
    return n


def dpid_hex(dpid: Any) -> str:
    return f"{normalize_dpid(dpid):016x}"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class RuleSpec:
    """A normalized rule. Build with ``RuleSpec.create`` (normalizes) rather than the constructor."""

    table_id: int
    priority: int
    match: Dict[str, Any]
    instructions: Tuple[Dict[str, Any], ...]

    @staticmethod
    def create(table_id: Any, priority: Any, match: Mapping[str, Any], instructions: Sequence[Mapping[str, Any]]) -> "RuleSpec":
        t, p = _to_int(table_id, "table_id"), _to_int(priority, "priority")
        if not 0 <= t <= 254:
            raise CanonicalError(f"table_id out of range: {t}")
        if not 0 <= p <= 65535:
            raise CanonicalError(f"priority out of range: {p}")
        return RuleSpec(t, p, normalize_match(match), tuple(normalize_instructions(instructions)))

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "RuleSpec":
        try:
            return RuleSpec.create(d["table"] if "table" in d else d["table_id"], d["priority"], d.get("match", {}),
                                   d.get("instructions", []))
        except KeyError as exc:
            raise CanonicalError(f"rule is missing {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        return {"table_id": self.table_id, "priority": self.priority, "match": self.match,
                "instructions": list(self.instructions)}

    def match_key(self) -> str:
        return _dumps(self.match)

    def key(self) -> Tuple[int, int, str]:
        """Identity of the rule slot in a switch: (table, priority, canonical match)."""
        return (self.table_id, self.priority, self.match_key())

    def content_key(self) -> str:
        """Canonical text of everything that defines behavior; two rules with equal content_key behave the same."""
        return _dumps(self.to_dict())

    def canonical_bytes(self, dpid: Any, epoch: int) -> bytes:
        if not 0 <= epoch <= 0xFFFF:
            raise CanonicalError(f"epoch out of range: {epoch}")
        body = {"dpid": normalize_dpid(dpid), "epoch": epoch, **self.to_dict()}
        return CANONICAL_VERSION + b"|" + _dumps(body).encode("ascii")

    def describe(self) -> str:
        m = ",".join(f"{k}={v}" for k, v in self.match.items()) or "*"
        return f"table={self.table_id} priority={self.priority} match[{m}]"
