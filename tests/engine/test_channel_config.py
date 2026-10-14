"""Event channel (real ZeroMQ) and engine config loading. Runs in .venv-engine (needs pyzmq)."""
import json
import os
import time

import pytest

zmq = pytest.importorskip("zmq")

from engine.channel import EventChannel  # noqa: E402
from engine.config import load_config  # noqa: E402


def pull_socket(endpoint):
    s = zmq.Context.instance().socket(zmq.PULL)
    s.setsockopt(zmq.LINGER, 0)
    s.bind(endpoint)
    return s


def recv_all(sock, n, timeout=2.0):
    out, end = [], time.time() + timeout
    while len(out) < n and time.time() < end:
        if sock.poll(50):
            out.append(json.loads(sock.recv()))
    return out


def test_events_flow_to_a_listening_core(tmp_path):
    ep = f"ipc://{tmp_path}/ev.ipc"
    pull = pull_socket(ep)
    ch = EventChannel(ep)
    try:
        for i in range(5):
            assert ch.publish({"i": i})
        deadline = time.time() + 2
        while ch.health()["sent_total"] < 5 and time.time() < deadline:
            ch.pump_once()
            time.sleep(0.02)
        assert [e["i"] for e in recv_all(pull, 5)] == [0, 1, 2, 3, 4]
    finally:
        ch.close()
        pull.close()


def test_publish_never_blocks_and_drops_are_counted_when_nobody_listens(tmp_path):
    ch = EventChannel(f"ipc://{tmp_path}/nobody.ipc", maxsize=10)
    try:
        t0 = time.time()
        results = [ch.publish({"i": i}) for i in range(50)]
        ch.pump_once()  # nobody connected: ZeroMQ buffers or refuses, but the call never blocks
        assert time.time() - t0 < 1.0
        assert results.count(True) == 10 and ch.dropped_total == 40  # bounded queue: overflow is dropped AND counted
    finally:
        ch.close()


def test_queued_events_are_delivered_once_the_core_appears(tmp_path):
    ep = f"ipc://{tmp_path}/late.ipc"
    ch = EventChannel(ep)
    try:
        ch.publish({"hello": 1})
        ch.pump_once()
        pull = pull_socket(ep)  # core starts late
        try:
            deadline = time.time() + 3
            while ch.health()["queued"] and time.time() < deadline:
                ch.pump_once()
                time.sleep(0.05)
            assert recv_all(pull, 1) == [{"hello": 1}]
        finally:
            pull.close()
    finally:
        ch.close()


def test_unserializable_event_is_dropped_not_raised(tmp_path):
    ch = EventChannel(f"ipc://{tmp_path}/x.ipc")
    try:
        class Bad:
            def __repr__(self):
                raise RuntimeError("boom")
        assert ch.publish({"x": Bad()}) is False and ch.dropped_total == 1
    finally:
        ch.close()


def test_config_defaults_and_paths_are_resolved(monkeypatch, tmp_path):
    monkeypatch.setenv("FLOWGUARD_CONFIG", str(tmp_path / "none.yaml"))
    cfg = load_config()
    assert cfg.critical_tables == [0] and os.path.isabs(cfg.db_path) and os.path.isabs(cfg.spool_path)
    assert cfg.event_endpoint.startswith("ipc:///")
    assert cfg.monitor_port(1) == 6634 and cfg.monitor_port(2) == 6635


def test_config_file_env_override_and_validation(monkeypatch, tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("engine:\n  grace_window_ms: 123\n  critical_tables: [0, 2]\nspool:\n  max_bytes: 4096\n  backups: 2\n")
    monkeypatch.setenv("FLOWGUARD_CONFIG", str(f))
    monkeypatch.setenv("FLOWGUARD_RECONCILE_S", "9")
    cfg = load_config()
    assert (cfg.grace_window_ms, cfg.critical_tables, cfg.spool_max_bytes, cfg.spool_backups, cfg.reconcile_poll_seconds) == (123, [0, 2], 4096, 2, 9.0)
    monkeypatch.setenv("FLOWGUARD_DATA_DIR", str(tmp_path / "d"))
    c2 = load_config()
    assert c2.db_path == str(tmp_path / "d" / "engine" / "golden.db") and c2.event_endpoint == f"ipc://{tmp_path}/d/run/events.ipc"
    f.write_text("engine:\n  nope: 1\n")
    with pytest.raises(ValueError, match="unknown"):
        load_config()
    f.write_text("engine:\n  response_mode: yolo\n")
    with pytest.raises(ValueError):
        load_config()
