"""Phase 5 pure logic: risk fusion, L3 anomaly baseline, L2 probe planning and judging."""
import pytest

from engine.anomaly import AnomalyScorer, action_class
from engine.canonical import RuleSpec
from engine.policy import load_policy, rules_for
from engine.prober import ProbeSpec, judge, plan_probes
from engine.risk import DEFAULT_DOC, RiskPolicy, fuse


def pol(**over):
    return RiskPolicy.from_doc({**DEFAULT_DOC, **over})


# ---- risk engine ------------------------------------------------------------------------------------------------------
def test_dry_run_records_the_action_but_does_nothing():
    d = fuse(pol(dry_run=True), 1, 1, 0)
    assert d.severity == "critical" and d.action == "restore_and_alert" and d.effective_action == "none"


def test_live_mode_acts_on_l1_plus_l2():
    d = fuse(pol(dry_run=False), 1, 1, 0.5)
    assert d.effective_action == "restore_and_alert" and not d.capped


def test_ml_alone_never_repairs():
    p = pol(dry_run=False, weights={"l1": 0.1, "l2": 0.1, "l3": 1.0}, thresholds={"alert": 0.1, "restore": 0.2, "quarantine": 0.3})
    d = fuse(p, 0, 0, 1.0)
    assert d.severity == "critical" and d.capped and d.effective_action == "alert_only"


def test_below_alert_threshold_does_nothing_and_weights_are_normalised():
    assert fuse(pol(dry_run=False), 0, 0, 0.2).effective_action == "none"
    assert fuse(pol(weights={"l1": 1, "l2": 0, "l3": 0}), 1, 1, 1).score == 1.0


@pytest.mark.parametrize("bad", [{"thresholds": {"alert": 0.9, "restore": 0.5, "quarantine": 0.8}},
                                 {"weights": {"l1": 0, "l2": 0, "l3": 0}},
                                 {"actions": {"critical": "explode", "high": "none", "medium": "none", "low": "none"}}])
def test_invalid_policy_documents_are_refused(bad):
    with pytest.raises(ValueError):
        pol(**bad)


# ---- L3 anomaly baseline ----------------------------------------------------------------------------------------------------
def trained():
    s = AnomalyScorer()
    for i in range(40):  # legitimate churn: a few forward/goto rules around priorities 80-110, one change every ~minute
        s.learn({"dpid": "1", "t": 1000.0 + i * 70, "priority": 80 + (i % 4) * 10, "action_class": "goto" if i % 3 else "forward"})
    return s


def test_baseline_not_ready_stays_low_and_says_so():
    score, reasons = AnomalyScorer().score({"dpid": "1", "t": 1.0, "priority": 100, "action_class": "drop", "signed": True})
    assert score == 0.0 and any("learning" in r for r in reasons)


def test_normal_change_scores_low_and_odd_change_scores_high():
    s = trained()
    normal, _ = s.score({"dpid": "1", "t": 5000.0, "priority": 90, "action_class": "goto", "signed": True})
    odd, why = s.score({"dpid": "1", "t": 5000.0, "priority": 60000, "action_class": "drop", "signed": True})
    assert normal < 0.2 and odd > 0.6 and why


def test_unsigned_rule_is_flagged_even_before_the_baseline_is_ready():
    score, why = AnomalyScorer().score({"dpid": "1", "t": 1.0, "priority": 1, "action_class": "goto", "signed": False})
    assert score >= 0.6 and any("not signed" in r for r in why)


def test_baseline_round_trips_through_json():
    s = trained()
    s2 = AnomalyScorer.from_json(s.to_json())
    ev = {"dpid": "1", "t": 5000.0, "priority": 60000, "action_class": "drop", "signed": True}
    assert s.score(ev) == s2.score(ev)


def test_action_class():
    assert action_class([]) == "drop" and action_class([{"type": "goto_table", "table_id": 1}]) == "goto"
    assert action_class([{"type": "apply_actions", "actions": []}]) == "forward"


# ---- L2 probes ----------------------------------------------------------------------------------------------------
def lab_rules():
    return rules_for(load_policy("engine/policies/lab_default.yaml"), 1)


def test_probe_plan_covers_the_lab_policy_and_picks_the_right_rule_per_packet():
    probes = plan_probes(lab_rules())
    by_prio = {p.priority: p for p in probes}
    assert by_prio[100].expect == "drop" and by_prio[100].fields["tcp_dst"] == 23
    assert by_prio[90].expect == "goto" and by_prio[90].fields["tcp_dst"] == 22
    # the default rule's synthesized packet is not caught by a higher-priority rule, so it is probed too
    assert by_prio[0].expect == "goto"


def test_a_rule_shadowed_by_the_policy_itself_is_not_probed():
    rules = [RuleSpec.create(0, 100, {"eth_type": 0x0800}, []), RuleSpec.create(0, 50, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 22}, [])]
    assert [p.priority for p in plan_probes(rules)] == [100]


def test_unsupported_match_fields_are_skipped_not_guessed():
    assert plan_probes([RuleSpec.create(0, 10, {"vlan_vid": 5}, [])]) == []
    assert plan_probes([RuleSpec.create(0, 10, {"eth_type": 0x0800, "ip_proto": 132}, [])]) == []  # SCTP: no packet builder


def spec(expect="drop"):
    return ProbeSpec(0, 100, "{}", expect, {}, "r")


def test_judge_pass_fail_and_inconclusive():
    assert judge(spec(), 3, 10, 13, 0).status == "pass"
    f = judge(spec(), 3, 10, 10, 0)  # counter did not move: the probe never hit the signed rule
    assert f.status == "fail" and f.l2 == 1.0 and "forwarding differs" in f.reason
    assert judge(spec("drop"), 3, 10, 13, 2).status == "fail"      # a packet that must be dropped came back
    assert judge(spec("goto"), 3, 10, 13, 2).status == "pass"      # goto legitimately reaches table 1's controller miss
    assert judge(spec(), 3, None, None, 0).status == "inconclusive"


# ---- port quarantine ------------------------------------------------------------------------------------------------------
def test_quarantine_only_ever_targets_a_real_port_named_by_the_rule():
    from engine.risk import quarantine_port
    assert quarantine_port({"in_port": 3, "eth_type": 0x0800}) == 3
    assert quarantine_port({"eth_type": 0x0800}) is None            # no port named: never guess
    assert quarantine_port({"in_port": 0}) is None                   # not a real port
    assert quarantine_port({"in_port": 0xFFFFFFFD}) is None          # reserved port (CONTROLLER-range): never cut
    assert quarantine_port({}) is None and quarantine_port(None) is None


# ---- wider probe coverage ------------------------------------------------------------------------------------------------------
def probe_for(match, instructions=()):
    probes = plan_probes([RuleSpec.create(0, 50, match, list(instructions))])
    assert len(probes) == 1, match
    return probes[0]


def test_probes_cover_icmp_arp_ipv6_in_port_mac_and_masked_addresses():
    assert probe_for({"eth_type": 0x0800, "ip_proto": 1}).fields["icmpv4_type"] == 8
    arp = probe_for({"eth_type": 0x0806, "arp_op": 1})
    assert arp.fields["eth_type"] == 0x0806 and arp.fields["arp_spa"]
    v6 = probe_for({"eth_type": 0x86DD, "ip_proto": 17, "udp_dst": 53})
    assert v6.fields["ipv6_src"] and v6.fields["udp_dst"] == 53 and "tcp_dst" not in v6.fields
    assert probe_for({"in_port": 3}).fields["in_port"] == 3
    assert probe_for({"eth_dst": "aa:bb:cc:dd:ee:01"}).fields["eth_dst"] == "aa:bb:cc:dd:ee:01"
    masked = probe_for({"eth_type": 0x0800, "ipv4_dst": "10.0.0.0/24"}, [{"type": "goto_table", "table_id": 1}])
    assert masked.fields["ipv4_dst"] == "10.0.0.0" and masked.expect == "goto"


def test_masked_rule_matching_honours_the_mask():
    from engine.prober import matches
    rule = RuleSpec.create(0, 5, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.0/24"}, []).match
    assert matches(rule, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.77"})
    assert not matches(rule, {"eth_type": 0x0800, "ipv4_dst": "10.0.1.1"})


def test_a_broader_higher_priority_rule_suppresses_the_narrower_probe_it_would_swallow():
    rules = [RuleSpec.create(0, 90, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.0/24"}, []),
             RuleSpec.create(0, 60, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.5"}, [])]
    assert [p.priority for p in plan_probes(rules)] == [90]


# ---- review fixes ------------------------------------------------------------------------------------------------------------
def test_failed_signature_never_scores_below_restore_even_with_the_default_weights():
    d = fuse(pol(dry_run=False), 1, 0, 0)  # L1 only: the plain weighted mean is 0.45, below the restore threshold
    assert d.score >= 0.5 and d.severity == "high" and d.effective_action == "restore_and_alert"


def test_probe_markers_round_trip_and_garbage_is_ignored():
    from engine.prober import make_marker, parse_marker
    assert parse_marker(b"xx" + make_marker("a1b2c3", 7) + b"yy") == ("a1b2c3", 7)
    for bad in (b"", b"FGPROBE", b"FGPROBE:only;", b"FGPROBE:n:notanint;", b"FGPROBE:\xff\xfe:1;"):
        assert parse_marker(bad) is None


def test_policy_may_not_use_the_quarantine_priority_range():
    from engine.policy import PolicyError, parse_policy
    parse_policy({"rules": [{"table": 0, "priority": 64999, "match": {}, "instructions": []}]})
    with pytest.raises(PolicyError, match="reserved"):
        parse_policy({"rules": [{"table": 0, "priority": 65000, "match": {"in_port": 2}, "instructions": []}]})


def test_baseline_is_bounded_and_a_damaged_file_never_crashes_loading(tmp_path):
    from engine.anomaly import MAX_SAMPLES
    s = AnomalyScorer()
    for i in range(MAX_SAMPLES + 50):
        s.learn({"dpid": "1", "t": float(i), "priority": i % 10, "action_class": "goto"})
    assert len(s.priorities) == MAX_SAMPLES and len(s.rates) == MAX_SAMPLES
    bad = tmp_path / "bad.json"
    bad.write_text('{"rates": 5, "priorities": 1, "classes": []}')
    assert AnomalyScorer.load(str(bad)).ready is False
    s.save(str(tmp_path / "sub" / "ok.json"))
    assert AnomalyScorer.load(str(tmp_path / "sub" / "ok.json")).ready
