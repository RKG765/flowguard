"""Golden store, alert spool, monitor-line parser and policy loading."""
import json
import os

import pytest

from engine.canonical import RuleSpec
from engine.crypto import EpochPolicy
from engine.monitor_parser import MonitorParser
from engine.policy import PolicyError, diff, load_policy, parse_policy, rules_for
from engine.spool import AlertSpool
from engine.store import GoldenStore, StoreCorrupt

R1 = RuleSpec.create(0, 100, {"tcp_dst": 23, "eth_type": 0x0800, "ip_proto": 6}, [])
R2 = RuleSpec.create(0, 0, {}, [{"type": "goto_table", "table_id": 1}])


# ---- store ---------------------------------------------------------------------------------------------------
def test_store_put_get_delete_list(tmp_path):
    s = GoldenStore(str(tmp_path / "g.db"))
    cookie = 0xFFFFFFFFFFFFFFFF  # needs all 64 bits
    s.put(1, R1, 3, cookie, now=5.0)
    s.put("0000000000000002", R2, 3, 7)
    g = s.get(1, R1)
    assert g.cookie == cookie and g.epoch == 3 and g.spec.content_key() == R1.content_key() and g.installed_at == 5.0
    assert [x.spec.key() for x in s.list(1)] == [R1.key()]
    assert s.dpids() == ["0000000000000001", "0000000000000002"]
    assert s.delete(1, R1) and not s.delete(1, R1)
    assert s.get(1, R1) is None and s.count() == 1


def test_store_replace_same_key(tmp_path):
    s = GoldenStore(str(tmp_path / "g.db"))
    s.put(1, R1, 1, 10)
    s.put(1, R1, 2, 20)
    assert s.count() == 1 and s.get(1, R1).cookie == 20


def test_store_persists_across_reopen_and_keeps_epoch_policy(tmp_path):
    p = str(tmp_path / "g.db")
    s = GoldenStore(p)
    s.put(1, R1, 1, 99)
    pol = EpochPolicy(current=4, previous=3, rotated_at=12.0, grace_seconds=300)
    s.save_epoch_policy(pol)
    s.close()
    s2 = GoldenStore(p)
    assert s2.get(1, R1).cookie == 99 and s2.integrity_check()
    q = s2.load_epoch_policy(grace_seconds=60)
    assert (q.current, q.previous, q.rotated_at, q.grace_seconds) == (4, 3, 12.0, 60)


def test_corrupt_database_is_reported_not_guessed(tmp_path):
    p = tmp_path / "g.db"
    p.write_bytes(b"this is not a sqlite database" * 100)
    with pytest.raises(StoreCorrupt):
        GoldenStore(str(p))


# ---- spool ---------------------------------------------------------------------------------------------------
def test_spool_sequence_ack_and_replay(tmp_path):
    sp = AlertSpool(str(tmp_path / "alerts.jsonl"))
    seqs = [sp.append({"kind": "forged", "n": i}).seq for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]
    sp.ack(3)
    assert [r["seq"] for r in sp.unacked()] == [4, 5]
    sp.ack(2)  # never moves backwards
    assert sp.acked() == 3
    again = AlertSpool(str(tmp_path / "alerts.jsonl"))  # restart: sequence continues, ack remembered
    assert again.append({"kind": "x"}).seq == 6 and [r["seq"] for r in again.unacked()] == [4, 5, 6]


def test_spool_file_mode_is_private(tmp_path):
    p = tmp_path / "alerts.jsonl"
    AlertSpool(str(p)).append({"a": 1})
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"


def test_spool_rotation_and_size_cap(tmp_path):
    sp = AlertSpool(str(tmp_path / "a.jsonl"), max_bytes=2048, backups=2)
    for i in range(200):
        sp.append({"i": i, "pad": "x" * 100})
    files = sorted(f for f in os.listdir(tmp_path) if f.startswith("a.jsonl") and not f.endswith(".ack"))
    assert files == ["a.jsonl", "a.jsonl.1", "a.jsonl.2"]
    assert sp.total_bytes() <= 3 * 2048
    assert sp.dropped_total > 0  # nothing was acknowledged, so dropped records are counted, not silent


def test_spool_overflow_reported_by_append(tmp_path):
    sp = AlertSpool(str(tmp_path / "a.jsonl"), max_bytes=1024, backups=1)
    results = [sp.append({"pad": "y" * 200}) for _ in range(30)]
    assert any(r.overflowed and r.dropped > 0 for r in results)
    assert sum(r.dropped for r in results) == sp.dropped_total


def test_spool_acked_records_are_not_counted_as_dropped(tmp_path):
    sp = AlertSpool(str(tmp_path / "a.jsonl"), max_bytes=1024, backups=1)
    for _ in range(40):
        r = sp.append({"pad": "z" * 200})
        sp.ack(r.seq)
    assert sp.dropped_total == 0


def test_spool_survives_a_torn_last_line(tmp_path):
    p = tmp_path / "a.jsonl"
    sp = AlertSpool(str(p))
    sp.append({"ok": 1})
    with open(p, "ab") as fh:
        fh.write(b'{"seq": 2, "broken')  # simulated crash mid-write
    again = AlertSpool(str(p))
    assert again.append({"ok": 2}).seq == 2
    assert [r["ok"] for r in again.unacked() if "ok" in r] == [1, 2]


def test_spool_rejects_silly_limits(tmp_path):
    with pytest.raises(ValueError):
        AlertSpool(str(tmp_path / "a"), max_bytes=10)


# ---- monitor parser ----------------------------------------------------------------------------------------
SAMPLE = """\
NXST_FLOW_MONITOR reply (xid=0x6):
 event=ADDED table=0 cookie=0x1234 ip actions=resubmit(,1)
NXST_FLOW_MONITOR reply (xid=0x0):
 event=MODIFIED table=0 cookie=0x1234 ip
NXST_FLOW_MONITOR reply (xid=0x0):
 event=DELETED reason=delete table=0 cookie=0 ip,nw_dst=10.0.0.3
 event=ADDED table=1 cookie=0 dl_dst=00:00:00:00:00:01 actions=output:1
garbage line
"""


def test_monitor_parser_distinguishes_initial_dump_from_live_updates():
    p = MonitorParser()
    evs = [e for e in (p.feed(l, now=1.0) for l in SAMPLE.splitlines()) if e]
    assert [(e.event, e.table_id, e.cookie, e.initial) for e in evs] == [
        ("added", 0, 0x1234, True), ("modified", 0, 0x1234, False), ("deleted", 0, 0, False), ("added", 1, 0, False)]
    assert evs[2].reason == "delete" and evs[2].match_text == "ip,nw_dst=10.0.0.3"
    assert evs[1].match_text == "ip"


def test_monitor_parser_ignores_noise():
    p = MonitorParser()
    assert p.feed("OFPT_ERROR (xid=0x6): something") is None
    assert p.feed("") is None
    assert p.feed(" event=PAUSED").event == "paused"


# ---- policy --------------------------------------------------------------------------------------------------
POLICY = {"rules": [
    {"table": 0, "priority": 100, "match": {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, "instructions": []},
    {"table": 0, "priority": 0, "match": {}, "instructions": [{"type": "goto_table", "table_id": 1}], "dpids": ["0000000000000002"]},
]}


def test_parse_policy_and_dpid_scoping():
    pol = parse_policy(POLICY)
    assert len(rules_for(pol, 1)) == 1 and len(rules_for(pol, 2)) == 2


@pytest.mark.parametrize("bad", [
    {}, {"rules": "x"}, {"rules": [1]}, {"rules": [{"priority": 1}]},
    {"rules": [{"table": 0, "priority": 1, "match": {"tcp_dst": "no"}}]},
    {"rules": [{"table": 0, "priority": 1, "match": {}}, {"table": 0, "priority": 1, "match": {}}]},
])
def test_bad_policies_rejected(bad):
    with pytest.raises(PolicyError):
        parse_policy(bad)


def test_policy_diff():
    a, b = [R1], [R1, R2]
    assert diff(a, b) == ([R2], [])
    assert diff(b, a) == ([], [R2])
    changed = RuleSpec.create(0, 100, R1.match, [{"type": "goto_table", "table_id": 1}])
    assert diff([R1], [changed]) == ([changed], [])


def test_load_default_policy_file():
    from pathlib import Path
    pol = load_policy(str(Path(__file__).resolve().parents[2] / "engine" / "policies" / "lab_default.yaml"))
    assert {r.spec.priority for r in pol} == {100, 90, 0}


def test_load_policy_errors(tmp_path):
    with pytest.raises(PolicyError):
        load_policy(str(tmp_path / "missing.yaml"))
    bad = tmp_path / "p.yaml"
    bad.write_text("rules: [unclosed")
    with pytest.raises(PolicyError):
        load_policy(str(bad))
    j = tmp_path / "p.json"
    j.write_text(json.dumps(POLICY))
    assert len(load_policy(str(j))) == 2
