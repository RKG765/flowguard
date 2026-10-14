"""Translate between normalized rules (``canonical.RuleSpec``) and Ryu OpenFlow 1.3 objects.

Needs the Ryu venv. Reading works from ``to_jsondict()`` so a stats reply is parsed the same way whatever the
exact Ryu class; anything this module does not model becomes a ``raw`` action/instruction that is compared
verbatim (so unknown content can still be detected as *different*, just not interpreted).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .canonical import OFPP_CONTROLLER, CanonicalError, RuleSpec
from .verifier import ObservedRule


# ---- reading --------------------------------------------------------------------------------------------------
def _tlv(d: Mapping[str, Any]) -> Dict[str, Any]:
    return d["OXMTlv"]


def match_fields(match: Any) -> Dict[str, Any]:
    """OFPMatch -> {field: value | [value, mask]}"""
    fields = match.to_jsondict()["OFPMatch"]["oxm_fields"]
    out: Dict[str, Any] = {}
    for f in fields:
        t = _tlv(f)
        out[t["field"]] = t["value"] if t.get("mask") is None else [t["value"], t["mask"]]
    return out


def _action(a: Mapping[str, Any]) -> Dict[str, Any]:
    (cls, body), = a.items()
    if cls == "OFPActionOutput":
        return {"type": "output", "port": body["port"], "max_len": body["max_len"]}
    if cls == "OFPActionSetField":
        t = _tlv(body["field"])
        return {"type": "set_field", "field": t["field"], "value": t["value"] if t.get("mask") is None else [t["value"], t["mask"]]}
    if cls == "OFPActionGroup":
        return {"type": "group", "group_id": body["group_id"]}
    if cls == "OFPActionSetQueue":
        return {"type": "set_queue", "queue_id": body["queue_id"]}
    if cls == "OFPActionPushVlan":
        return {"type": "push_vlan", "ethertype": body["ethertype"]}
    if cls == "OFPActionPopVlan":
        return {"type": "pop_vlan"}
    if cls == "OFPActionDecNwTtl":
        return {"type": "dec_nw_ttl"}
    params = {k: v for k, v in body.items() if k not in ("len", "type")}
    return {"type": "raw", "class": cls, "params": params}


def _instruction(i: Mapping[str, Any]) -> Dict[str, Any]:
    (cls, body), = i.items()
    if cls == "OFPInstructionGotoTable":
        return {"type": "goto_table", "table_id": body["table_id"]}
    if cls == "OFPInstructionActions":
        t = body["type"]  # 3 write, 4 apply, 5 clear (OFPIT_*)
        if t == 5:
            return {"type": "clear_actions"}
        return {"type": "apply_actions" if t == 4 else "write_actions", "actions": [_action(a) for a in body["actions"]]}
    if cls == "OFPInstructionMeter":
        return {"type": "meter", "meter_id": body["meter_id"]}
    if cls == "OFPInstructionWriteMetadata":
        return {"type": "write_metadata", "metadata": body["metadata"], "mask": body["metadata_mask"]}
    raise CanonicalError(f"unsupported instruction class {cls}")


def stat_to_observed(stat: Any) -> ObservedRule:
    """OFPFlowStats -> ObservedRule. Raises CanonicalError when the rule cannot be normalized."""
    ins = [_instruction(i.to_jsondict()) for i in stat.instructions]
    spec = RuleSpec.create(stat.table_id, stat.priority, match_fields(stat.match), ins)
    return ObservedRule(spec, int(stat.cookie))


# ---- writing --------------------------------------------------------------------------------------------------
def _field_arg(v: Any) -> Any:
    return tuple(v) if isinstance(v, list) else v


def build_match(parser: Any, spec: RuleSpec) -> Any:
    return parser.OFPMatch(**{k: _field_arg(v) for k, v in spec.match.items()})


def _build_action(parser: Any, a: Mapping[str, Any]) -> Any:
    t = a["type"]
    if t == "output":
        return parser.OFPActionOutput(a["port"], a.get("max_len", 0) if a["port"] == OFPP_CONTROLLER else 0)
    if t == "set_field":
        return parser.OFPActionSetField(**{a["field"]: _field_arg(a["value"])})
    if t == "group":
        return parser.OFPActionGroup(a["group_id"])
    if t == "set_queue":
        return parser.OFPActionSetQueue(a["queue_id"])
    if t == "push_vlan":
        return parser.OFPActionPushVlan(a["ethertype"])
    if t == "pop_vlan":
        return parser.OFPActionPopVlan()
    if t == "dec_nw_ttl":
        return parser.OFPActionDecNwTtl()
    raise CanonicalError(f"cannot build action {t!r}")


def build_instructions(dp: Any, spec: RuleSpec) -> List[Any]:
    ofp, parser = dp.ofproto, dp.ofproto_parser
    out: List[Any] = []
    for ins in spec.instructions:
        t = ins["type"]
        if t == "goto_table":
            out.append(parser.OFPInstructionGotoTable(ins["table_id"]))
        elif t in ("apply_actions", "write_actions"):
            kind = ofp.OFPIT_APPLY_ACTIONS if t == "apply_actions" else ofp.OFPIT_WRITE_ACTIONS
            out.append(parser.OFPInstructionActions(kind, [_build_action(parser, a) for a in ins["actions"]]))
        elif t == "clear_actions":
            out.append(parser.OFPInstructionActions(ofp.OFPIT_CLEAR_ACTIONS, []))
        elif t == "meter":
            out.append(parser.OFPInstructionMeter(ins["meter_id"]))
        elif t == "write_metadata":
            out.append(parser.OFPInstructionWriteMetadata(ins["metadata"], ins["mask"]))
        else:
            raise CanonicalError(f"cannot build instruction {t!r}")
    return out


def flow_add(dp: Any, spec: RuleSpec, cookie: int) -> Any:
    """OFPFC_ADD: atomically creates the rule or replaces an existing rule with the same table/priority/match."""
    return dp.ofproto_parser.OFPFlowMod(
        datapath=dp, cookie=cookie, cookie_mask=0, table_id=spec.table_id, command=dp.ofproto.OFPFC_ADD,
        priority=spec.priority, match=build_match(dp.ofproto_parser, spec), instructions=build_instructions(dp, spec))


def flow_delete_strict(dp: Any, spec: RuleSpec) -> Any:
    ofp = dp.ofproto
    return dp.ofproto_parser.OFPFlowMod(
        datapath=dp, cookie=0, cookie_mask=0, table_id=spec.table_id, command=ofp.OFPFC_DELETE_STRICT,
        out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY, priority=spec.priority, match=build_match(dp.ofproto_parser, spec))


def flow_stats_request(dp: Any, table_id: int) -> Any:
    ofp, parser = dp.ofproto, dp.ofproto_parser
    return parser.OFPFlowStatsRequest(dp, 0, table_id, ofp.OFPP_ANY, ofp.OFPG_ANY, 0, 0, parser.OFPMatch())
