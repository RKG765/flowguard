"""HMAC cookies: sign/verify, binding to dpid/epoch/content, rotation window, key-file hygiene."""
import os
import stat

import pytest
from hypothesis import given, settings, strategies as st

from engine.canonical import RuleSpec
from engine.crypto import (EpochPolicy, KeyMaterialError, Signer, generate_key_file, key_fingerprint, load_master_key)

KEY = bytes(range(32))
RULE = RuleSpec.create(0, 100, {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 23}, [])


def signer(**kw):
    return Signer(KEY, EpochPolicy(**kw))


def test_roundtrip_and_cookie_layout():
    s = signer(current=7)
    c = s.cookie_for(1, RULE)
    assert c & 0xFFFF == 7 and 0 < c < 1 << 64
    assert s.verify(1, RULE, c, now=0).valid


def test_different_dpid_content_or_key_fails():
    s = signer()
    c = s.cookie_for(1, RULE)
    assert not s.verify(2, RULE, c).valid                                   # other switch
    assert not s.verify(1, RuleSpec.create(0, 101, RULE.match, []), c).valid  # other priority
    assert not s.verify(1, RuleSpec.create(1, 100, RULE.match, []), c).valid  # other table
    assert not s.verify(1, RuleSpec.create(0, 100, RULE.match, [{"type": "goto_table", "table_id": 1}]), c).valid
    assert not Signer(bytes(32)).verify(1, RULE, c).valid                   # other key


def test_flipping_any_cookie_bit_fails():
    s = signer()
    c = s.cookie_for(1, RULE)
    for bit in range(16, 64):  # tag bits
        assert not s.verify(1, RULE, c ^ (1 << bit)).valid
    for bit in range(16):      # epoch bits
        assert not s.verify(1, RULE, c ^ (1 << bit)).valid


def test_zero_and_out_of_range_cookie():
    s = signer()
    assert s.verify(1, RULE, 0).reason == "zero_cookie"
    assert not s.verify(1, RULE, 1 << 64).valid
    assert not s.verify(1, RULE, -1).valid


def test_rotation_window():
    s = signer(current=1, grace_seconds=300)
    old = s.cookie_for(1, RULE)
    s.policy.rotate(now=1000.0)
    assert s.policy.current == 2
    new = s.cookie_for(1, RULE)
    assert new != old
    assert s.verify(1, RULE, old, now=1100.0).valid       # inside the window
    assert s.verify(1, RULE, new, now=1100.0).valid
    late = s.verify(1, RULE, old, now=1301.0)             # window over: replayed old signed rule is rejected
    assert not late.valid and late.reason == "bad_epoch"
    assert s.verify(1, RULE, new, now=99999.0).valid


def test_two_rotations_drop_the_oldest_epoch_immediately():
    s = signer(current=1)
    e1 = s.cookie_for(1, RULE)
    s.policy.rotate(10.0)
    s.policy.rotate(11.0)
    assert not s.verify(1, RULE, e1, now=12.0).valid


def test_epoch_wraps_at_16_bits():
    p = EpochPolicy(current=0xFFFF)
    assert p.rotate(1.0) == 0 and p.previous == 0xFFFF


def test_policy_persistence_roundtrip():
    p = EpochPolicy(current=3, previous=2, rotated_at=5.0, grace_seconds=60)
    q = EpochPolicy.from_dict(p.to_dict())
    assert (q.current, q.previous, q.rotated_at, q.grace_seconds) == (3, 2, 5.0, 60)


def test_repr_does_not_leak_key():
    assert KEY.hex() not in repr(signer()) and "Signer(" in repr(signer())


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 2 ** 64 - 1), st.integers(0, 254), st.integers(0, 65535), st.integers(0, 0xFFFF))
def test_property_valid_cookie_always_verifies_and_is_bound(dpid, table, prio, epoch):
    s = Signer(KEY, EpochPolicy(current=epoch))
    r = RuleSpec.create(table, prio, {"in_port": 1}, [])
    c = s.cookie_for(dpid, r)
    assert 0 <= c < 1 << 64 and s.verify(dpid, r, c, now=0).valid
    assert not s.verify((dpid + 1) % (1 << 64), r, c, now=0).valid


# ---- key files -------------------------------------------------------------------------------------------
def test_generate_and_load_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FLOWGUARD_HMAC_KEY", raising=False)
    p = str(tmp_path / "k" / "hmac.key")
    fp = generate_key_file(p)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    key = load_master_key(p)
    assert len(key) == 32 and key_fingerprint(key) == fp
    with pytest.raises(FileExistsError):
        generate_key_file(p)  # never overwrite an existing key


def test_loose_permissions_are_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("FLOWGUARD_HMAC_KEY", raising=False)
    p = tmp_path / "hmac.key"
    p.write_text("ab" * 32)
    os.chmod(p, 0o644)
    with pytest.raises(KeyMaterialError, match="0600"):
        load_master_key(str(p))


@pytest.mark.parametrize("content", ["", "zz" * 32, "ab" * 8])
def test_malformed_or_short_keys_are_refused(tmp_path, monkeypatch, content):
    monkeypatch.delenv("FLOWGUARD_HMAC_KEY", raising=False)
    p = tmp_path / "hmac.key"
    p.write_text(content)
    os.chmod(p, 0o600)
    with pytest.raises(KeyMaterialError):
        load_master_key(str(p))


def test_env_var_wins_and_missing_key_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWGUARD_HMAC_KEY", "cd" * 32)
    assert load_master_key(None) == bytes.fromhex("cd" * 32)
    monkeypatch.delenv("FLOWGUARD_HMAC_KEY")
    with pytest.raises(KeyMaterialError):
        load_master_key(None)
    with pytest.raises(KeyMaterialError, match="not found"):
        load_master_key(str(tmp_path / "absent.key"))
