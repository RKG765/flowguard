"""Canonical form: same logical rule -> same bytes; any behavior-relevant change -> different bytes."""
import pytest
from hypothesis import given, settings, strategies as st

from engine.canonical import (CanonicalError, RuleSpec, dpid_hex, matches_overlap, normalize_dpid, normalize_field,
                              normalize_match)

ACL = dict(table=0, priority=100, match={"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, instructions=[])


def spec(**over):
    d = dict(ACL, **over)
    return RuleSpec.from_dict(d)


def test_field_order_and_spelling_do_not_matter():
    a = RuleSpec.create(0, 100, {"tcp_dst": 23, "eth_type": 0x0800, "ip_proto": 6}, [])
    b = RuleSpec.create("0", "100", {"ip_proto": "6", "eth_type": "0x800", "tcp_dst": "23"}, [])
    assert a.canonical_bytes(1, 1) == b.canonical_bytes(1, 1)


def test_mac_and_ip_spellings_normalize():
    assert normalize_field("eth_dst", "AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_field("ipv4_dst", "10.0.0.3") == normalize_field("ipv4_dst", 0x0A000003)
    assert normalize_field("ipv4_dst", "10.0.0.7/24") == ["10.0.0.0", "255.255.255.0"]
    assert normalize_field("ipv4_dst", ["10.0.0.9", "255.255.255.0"]) == ["10.0.0.0", "255.255.255.0"]


def test_full_mask_equals_exact_match():
    assert normalize_field("ipv4_dst", "10.0.0.3/32") == "10.0.0.3"
    assert normalize_field("tcp_dst", [23, 0xFFFF]) == 23


def test_output_max_len_ignored_except_controller():
    a = RuleSpec.create(1, 10, {}, [{"type": "apply_actions", "actions": [{"type": "output", "port": 1, "max_len": 65509}]}])
    b = RuleSpec.create(1, 10, {}, [{"type": "apply_actions", "actions": [{"type": "output", "port": 1}]}])
    assert a.content_key() == b.content_key()
    c = RuleSpec.create(1, 10, {}, [{"type": "apply_actions", "actions": [{"type": "output", "port": "CONTROLLER"}]}])
    assert c.instructions[0]["actions"][0]["max_len"] == 0xFFFF


def test_apply_actions_order_matters_write_actions_order_does_not():
    out1, out2 = {"type": "output", "port": 1}, {"type": "output", "port": 2}
    apply_ab = RuleSpec.create(0, 1, {}, [{"type": "apply_actions", "actions": [out1, out2]}])
    apply_ba = RuleSpec.create(0, 1, {}, [{"type": "apply_actions", "actions": [out2, out1]}])
    write_ab = RuleSpec.create(0, 1, {}, [{"type": "write_actions", "actions": [out1, out2]}])
    write_ba = RuleSpec.create(0, 1, {}, [{"type": "write_actions", "actions": [out2, out1]}])
    assert apply_ab.content_key() != apply_ba.content_key()
    assert write_ab.content_key() == write_ba.content_key()


def test_instruction_order_is_the_openflow_execution_order():
    goto = {"type": "goto_table", "table_id": 1}
    app = {"type": "apply_actions", "actions": [{"type": "output", "port": 3}]}
    assert RuleSpec.create(0, 1, {}, [goto, app]).content_key() == RuleSpec.create(0, 1, {}, [app, goto]).content_key()


@pytest.mark.parametrize("change", [
    dict(priority=101), dict(table=1), dict(match={"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 24}),
    dict(instructions=[{"type": "goto_table", "table_id": 1}]),
])
def test_any_behavior_change_changes_bytes(change):
    assert spec().canonical_bytes(1, 1) != spec(**change).canonical_bytes(1, 1)


def test_dpid_and_epoch_are_bound_into_the_bytes():
    s = spec()
    assert s.canonical_bytes(1, 1) != s.canonical_bytes(2, 1)
    assert s.canonical_bytes(1, 1) != s.canonical_bytes(1, 2)
    assert s.canonical_bytes("0000000000000001", 1) == s.canonical_bytes(1, 1)


def test_cookie_counters_and_timeouts_are_not_part_of_the_spec():
    # the spec has no place for them: extra keys in the source dict are ignored by from_dict
    noisy = dict(ACL, cookie=0xDEAD, idle_timeout=5, packet_count=99)
    assert RuleSpec.from_dict(noisy).canonical_bytes(1, 1) == spec().canonical_bytes(1, 1)


@pytest.mark.parametrize("bad", [
    dict(table=300), dict(priority=70000), dict(match={"tcp_dst": "abc"}), dict(match={"eth_dst": "zz"}),
    dict(instructions=[{"type": "fly"}]), dict(instructions=[{"nope": 1}]),
])
def test_bad_rules_raise_canonical_error(bad):
    with pytest.raises(CanonicalError):
        spec(**bad)


def test_dpid_forms():
    assert normalize_dpid("0000000000000001") == normalize_dpid(1) == normalize_dpid("0x1") == 1
    assert dpid_hex(2) == "0000000000000002"
    for bad in (-1, 1 << 64, "xyz", None, True):
        with pytest.raises(CanonicalError):
            normalize_dpid(bad)


def test_overlap():
    telnet = normalize_match({"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23})
    host = normalize_match({"eth_type": 0x0800, "ipv4_dst": "10.0.0.3"})
    other_port = normalize_match({"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 22})
    subnet = normalize_match({"eth_type": 0x0800, "ipv4_dst": "10.0.0.0/24"})
    assert matches_overlap(telnet, host)          # a packet to 10.0.0.3:23 matches both
    assert not matches_overlap(telnet, other_port)
    assert matches_overlap(host, subnet)
    assert not matches_overlap(host, normalize_match({"ipv4_dst": "10.0.1.3"}))
    assert matches_overlap(telnet, {})            # empty match overlaps everything


field_names = st.sampled_from(["in_port", "eth_type", "ip_proto", "tcp_dst", "tcp_src", "udp_dst", "ip_dscp"])
matches = st.dictionaries(field_names, st.integers(0, 63), max_size=5)
actions = st.lists(st.sampled_from([{"type": "output", "port": p} for p in (1, 2, 3)]), max_size=3)


@settings(max_examples=150, deadline=None)
@given(matches, st.integers(0, 65535), st.integers(0, 254), actions, st.integers(0, 2 ** 64 - 1), st.integers(0, 0xFFFF))
def test_property_deterministic_and_order_independent(match, prio, table, acts, dpid, epoch):
    ins = [{"type": "apply_actions", "actions": acts}] if acts else []
    a = RuleSpec.create(table, prio, match, ins)
    shuffled = dict(reversed(list(match.items())))
    b = RuleSpec.create(table, prio, shuffled, ins)
    assert a.canonical_bytes(dpid, epoch) == b.canonical_bytes(dpid, epoch)
    assert a.key() == b.key()


@settings(max_examples=150, deadline=None)
@given(matches, st.integers(0, 65534), st.integers(0, 254))
def test_property_priority_change_changes_bytes(match, prio, table):
    a = RuleSpec.create(table, prio, match, [])
    b = RuleSpec.create(table, prio + 1, match, [])
    assert a.canonical_bytes(1, 1) != b.canonical_bytes(1, 1)
