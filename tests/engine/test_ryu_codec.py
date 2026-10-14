"""Ryu codec round trips (run in .venv-engine: needs Ryu). Goes through real Ryu classes and jsondict output."""
import pytest

pytest.importorskip("ryu")

from ryu.ofproto import ofproto_v1_3 as ofp, ofproto_v1_3_parser as parser  # noqa: E402

from engine import ryu_codec  # noqa: E402
from engine.canonical import RuleSpec  # noqa: E402


class DP:
    ofproto = ofp
    ofproto_parser = parser
    id = 1
    xid = None

    def set_xid(self, msg):
        msg.set_xid(1)


class FakeStat:
    """Stands in for OFPFlowStats: same attributes, built from a FlowMod we construct ourselves."""

    def __init__(self, mod):
        self.table_id, self.priority, self.cookie = mod.table_id, mod.priority, mod.cookie
        self.match, self.instructions = mod.match, mod.instructions


SPECS = [
    RuleSpec.create(0, 100, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, []),
    RuleSpec.create(0, 0, {}, [{"type": "goto_table", "table_id": 1}]),
    RuleSpec.create(0, 50, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.0/24", "eth_dst": "00:00:00:00:00:01"},
                    [{"type": "apply_actions", "actions": [
                        {"type": "set_field", "field": "eth_dst", "value": "aa:bb:cc:dd:ee:ff"},
                        {"type": "output", "port": 2}, {"type": "output", "port": "CONTROLLER", "max_len": 128},
                        {"type": "group", "group_id": 3}, {"type": "push_vlan", "ethertype": 0x8100},
                        {"type": "pop_vlan"}, {"type": "set_queue", "queue_id": 2}, {"type": "dec_nw_ttl"}]},
                     {"type": "goto_table", "table_id": 1}]),
    RuleSpec.create(1, 10, {"in_port": 3}, [{"type": "clear_actions"}, {"type": "meter", "meter_id": 2},
                                           {"type": "write_metadata", "metadata": 5, "mask": 255}]),
    RuleSpec.create(1, 20, {"in_port": 3}, [{"type": "write_actions", "actions": [{"type": "output", "port": 7}]}]),
]


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.describe())
def test_spec_to_flowmod_and_back_is_identity(spec):
    mod = ryu_codec.flow_add(DP(), spec, 0xABCDEF0123456789)
    obs = ryu_codec.stat_to_observed(FakeStat(mod))
    assert obs.spec.content_key() == spec.content_key()
    assert obs.cookie == 0xABCDEF0123456789


def test_output_max_len_reported_by_ovs_does_not_create_a_difference():
    # OVS reports max_len=65509 for ordinary outputs; the codec must not treat that as tampering
    spec = RuleSpec.create(1, 10, {}, [{"type": "apply_actions", "actions": [{"type": "output", "port": 5}]}])
    mod = ryu_codec.flow_add(DP(), spec, 1)
    assert mod.instructions[0].actions[0].max_len == 0
    mod.instructions[0].actions[0].max_len = 65509
    assert ryu_codec.stat_to_observed(FakeStat(mod)).spec.content_key() == spec.content_key()


def test_unknown_action_is_kept_verbatim_so_a_change_is_still_detected():
    spec = RuleSpec.create(0, 5, {}, [])
    mod = ryu_codec.flow_add(DP(), spec, 1)
    mod.instructions = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [parser.OFPActionPushMpls(0x8847)])]
    obs = ryu_codec.stat_to_observed(FakeStat(mod))
    assert obs.spec.instructions[0]["actions"][0]["type"] == "raw"
    assert obs.spec.content_key() != spec.content_key()


def test_delete_strict_and_stats_request_shapes():
    spec = SPECS[0]
    d = ryu_codec.flow_delete_strict(DP(), spec)
    assert d.command == ofp.OFPFC_DELETE_STRICT and d.priority == 100 and d.table_id == 0
    r = ryu_codec.flow_stats_request(DP(), 0)
    assert r.table_id == 0 and r.cookie_mask == 0
