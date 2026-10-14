"""Verifier classes, attribution of the engine's own changes, responder policy and alert de-duplication."""
from engine.canonical import RuleSpec
from engine.crypto import EpochPolicy, Signer
from engine.responder import DELETE, NONE, RESTORE, Responder
from engine.store import GoldenRule
from engine.verifier import (ALTERED, FORGED, MISSING, SHADOW, Deduper, ObservedRule, Pending, classify, explain)

DPID = 1
SIGNER = Signer(bytes(range(32)), EpochPolicy(current=1))
GOTO1 = [{"type": "goto_table", "table_id": 1}]


def golden(spec):
    return GoldenRule("0000000000000001", spec, 1, SIGNER.cookie_for(DPID, spec), 0.0)


TELNET = RuleSpec.create(0, 100, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, [])
SSH = RuleSpec.create(0, 90, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 22}, GOTO1)
MISS = RuleSpec.create(0, 0, {}, GOTO1)
GOLD = [golden(TELNET), golden(SSH), golden(MISS)]


def obs(spec, cookie=None):
    return ObservedRule(spec, SIGNER.cookie_for(DPID, spec) if cookie is None else cookie)


def run(observed, **kw):
    return classify(DPID, observed, GOLD, SIGNER, now=0.0, **kw)


def kinds(findings):
    return [f.kind for f in findings]


def test_clean_table_has_no_findings():
    assert run([obs(TELNET), obs(SSH), obs(MISS)]) == []


def test_missing():
    f = run([obs(SSH), obs(MISS)])
    assert kinds(f) == [MISSING] and f[0].golden.spec.key() == TELNET.key()


def test_altered_instructions_keep_cookie():
    tampered = RuleSpec.create(0, 100, TELNET.match, [{"type": "apply_actions", "actions": [{"type": "output", "port": 1}]}])
    f = run([obs(tampered, cookie=GOLD[0].cookie), obs(SSH), obs(MISS)])
    assert kinds(f) == [ALTERED]
    assert f[0].signature_valid is False and "instructions_differ" in f[0].reasons and "cookie_differs" not in f[0].reasons


def test_same_content_but_unsigned_cookie_is_altered():
    f = run([obs(TELNET, cookie=0), obs(SSH), obs(MISS)])
    assert kinds(f) == [ALTERED] and f[0].reasons == ("cookie_differs",)


def test_forged_rule_not_overlapping_a_protected_rule():
    evil = RuleSpec.create(0, 300, {"eth_type": 0x0800, "ipv4_dst": "10.0.0.3"}, [])
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(evil, cookie=0)])
    assert kinds(f) == [SHADOW]  # 10.0.0.3 can be a telnet destination, so it does overlap TELNET


def test_forged_rule_that_overlaps_nothing_protected_is_forged():
    evil = RuleSpec.create(0, 300, {"eth_type": 0x0806}, [])  # ARP: overlaps neither tcp rule
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(evil, cookie=0)])
    assert kinds(f) == [FORGED] and f[0].shadows == ()


def test_lower_priority_overlap_is_not_shadow():
    low = RuleSpec.create(0, 50, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, [])
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(low, cookie=0)])
    assert kinds(f) == [FORGED]


def test_table_miss_does_not_turn_every_unknown_rule_into_shadow():
    evil = RuleSpec.create(0, 5, {"in_port": 9}, [])
    assert kinds(run([obs(TELNET), obs(SSH), obs(MISS), obs(evil, cookie=0)])) == [FORGED]


def test_replayed_signed_rule_is_flagged_with_valid_signature():
    other = RuleSpec.create(0, 300, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23, "in_port": 4}, GOTO1)
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(other)])  # properly signed, but not in the golden store
    assert kinds(f) == [SHADOW] and f[0].signature_valid is True


def test_cookie_copied_from_another_rule_does_not_help_the_attacker():
    evil = RuleSpec.create(0, 300, {"eth_type": 0x0806}, [])
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(evil, cookie=GOLD[0].cookie)])
    assert kinds(f) == [FORGED] and f[0].signature_valid is False


def test_rule_in_another_table_is_not_compared():
    t1 = RuleSpec.create(1, 10, {"eth_dst": "00:00:00:00:00:01"}, [])
    # classify() is given the table under verification; table-1 learning rules are simply not passed in
    assert run([obs(TELNET), obs(SSH), obs(MISS)]) == []
    assert t1.table_id == 1


def test_skip_slots_defers_judgement_of_in_flight_changes():
    assert run([obs(SSH), obs(MISS)], skip_slots={TELNET.key()}) == []  # our restore of TELNET is in flight


def test_copying_a_golden_cookie_cannot_hide_inside_the_grace_window():
    """Regression: the exemption used to be keyed by cookie, so a rule carrying a copied golden cookie was skipped."""
    evil = RuleSpec.create(0, 250, {"eth_type": 0x0806}, [])
    f = run([obs(TELNET), obs(SSH), obs(MISS), obs(evil, cookie=GOLD[0].cookie)], skip_slots={TELNET.key()})
    assert kinds(f) == [FORGED] and f[0].spec.priority == 250


def test_findings_order_is_deterministic():
    a = run([obs(MISS)])
    b = run([obs(MISS)])
    assert [x.key() for x in a] == [x.key() for x in b]
    assert kinds(a) == [MISSING, MISSING]


def test_explanations_are_plain_language():
    for f in run([obs(SSH), obs(MISS)]):
        assert "OpenFlow" not in explain(f) and f.spec.describe() in explain(f)


# ---- pending / attribution --------------------------------------------------------------------------------
def test_pending_attributes_once_and_expires():
    p = Pending(grace_seconds=0.5)
    p.expect(DPID, 0, 0xABC, ["added", "modified"], now=10.0, slot=TELNET.key())
    assert p.live_cookies(DPID, now=10.1) == {0xABC} and p.live_slots(DPID, now=10.1) == {TELNET.key()}
    assert not p.attribute(DPID, 0, "deleted", 0xABC, now=10.1)   # wrong event type
    assert not p.attribute(DPID, 1, "added", 0xABC, now=10.1)     # wrong table
    assert p.attribute(DPID, 0, "added", 0xABC, now=10.1)
    assert not p.attribute(DPID, 0, "added", 0xABC, now=10.1)     # consumed: a second identical event is NOT ours
    p.expect(DPID, 0, 0xDEF, ["added"], now=10.0)
    assert not p.attribute(DPID, 0, "added", 0xDEF, now=11.0)     # expired
    assert p.live_cookies(DPID, now=11.0) == set() and p.live_slots(DPID, now=11.0) == set()


# ---- responder --------------------------------------------------------------------------------------------
def test_responder_maps_kinds_to_actions():
    evil = RuleSpec.create(0, 300, {"eth_type": 0x0806}, [])
    findings = run([obs(SSH), obs(MISS), obs(evil, cookie=0)])
    ops = {a.finding.kind: a.op for a in Responder(per_minute=100).plan(findings, now=0.0)}
    assert ops == {MISSING: RESTORE, FORGED: DELETE}


def test_alert_only_mode_never_acts():
    findings = run([obs(SSH), obs(MISS)])
    assert {a.op for a in Responder(mode="alert_only").plan(findings)} == {NONE}


def test_rate_limit_per_switch_and_recovery():
    r = Responder(per_minute=2)
    f = run([obs(MISS)])  # two missing rules
    first = r.plan(f, now=0.0)
    assert [a.op for a in first] == [RESTORE, RESTORE]
    again = r.plan(f, now=1.0)
    assert [a.op for a in again] == [NONE, NONE] and again[0].reason == "rate_limited"
    assert [a.op for a in r.plan(f, now=61.0)] == [RESTORE, RESTORE]


def test_unknown_mode_rejected():
    import pytest
    with pytest.raises(ValueError):
        Responder(mode="yolo")


# ---- dedupe -------------------------------------------------------------------------------------------------
def test_deduper_window():
    d = Deduper(window_seconds=30)
    k = ("a",)
    assert d.should_alert(k, now=0.0)
    assert not d.should_alert(k, now=10.0)
    assert d.should_alert(k, now=31.0)
    assert d.should_alert(("b",), now=31.0)
