"""Engine configuration: defaults, optional YAML file (FLOWGUARD_CONFIG or <repo>/config.yaml), env overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent


def _abs(p: str) -> str:
    q = os.path.expanduser(p)
    return q if os.path.isabs(q) else str(REPO / q)


@dataclass
class EngineConfig:
    critical_tables: List[int] = field(default_factory=lambda: [0])
    key_file: str = "~/.config/flowguard/hmac.key"
    db_path: str = "data/engine/golden.db"
    policy_path: str = "engine/policies/lab_default.yaml"
    spool_path: str = "data/spool/alerts.jsonl"
    spool_max_bytes: int = 10 * 1024 * 1024
    spool_backups: int = 5
    eventlog_path: str = "data/run/engine_events.jsonl"
    run_dir: str = "data/run"
    event_endpoint: str = "ipc://data/run/events.ipc"
    event_queue_max: int = 2000
    monitor_base_port: int = 6634       # dpid 1 -> base, dpid 2 -> base + 1, ...
    verify_mode: str = "event"          # event | poll
    reconcile_poll_seconds: float = 5.0
    grace_window_ms: int = 500
    verify_debounce_ms: int = 15
    stats_timeout_seconds: float = 3.0
    restore_rate_limit_per_minute: int = 30
    rotation_grace_seconds: float = 300.0
    response_mode: str = "restore"      # restore | alert_only (dry run)
    policy_poll_seconds: float = 1.0
    alert_dedupe_seconds: float = 30.0
    learning_switch: bool = True        # unsigned learning switch in table 1 (lab)

    def resolved(self) -> "EngineConfig":
        """Return a copy with every path made absolute (relative paths are relative to the repo root)."""
        c = EngineConfig(**{f.name: getattr(self, f.name) for f in fields(self)})
        for name in ("db_path", "policy_path", "spool_path", "eventlog_path", "run_dir"):
            setattr(c, name, _abs(getattr(c, name)))
        c.key_file = os.path.expanduser(c.key_file)
        if c.event_endpoint.startswith("ipc://"):
            c.event_endpoint = "ipc://" + _abs(c.event_endpoint[len("ipc://"):])
        return c

    def monitor_port(self, dpid: int) -> int:
        return self.monitor_base_port + max(0, dpid - 1)


def load_config(path: Optional[str] = None) -> EngineConfig:
    path = path or os.environ.get("FLOWGUARD_CONFIG") or str(REPO / "config.yaml")
    data: Dict[str, Any] = {}
    if os.path.exists(path):
        import yaml
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        data = dict(raw.get("engine", {}))
        spool = raw.get("spool", {}) or {}
        for src, dst in (("path", "spool_path"), ("max_bytes", "spool_max_bytes"), ("backups", "spool_backups")):
            if src in spool:
                data[dst] = spool[src]
        if (raw.get("secrets", {}) or {}).get("hmac_key_file"):
            data["key_file"] = raw["secrets"]["hmac_key_file"]
    valid = {f.name for f in fields(EngineConfig)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"unknown engine config keys: {sorted(unknown)}")
    cfg = EngineConfig(**data)
    for env, attr, cast in (("FLOWGUARD_KEY_FILE", "key_file", str), ("FLOWGUARD_DATA_DIR", None, str),
                            ("FLOWGUARD_POLICY", "policy_path", str), ("FLOWGUARD_RESPONSE_MODE", "response_mode", str),
                            ("FLOWGUARD_GRACE_MS", "grace_window_ms", int), ("FLOWGUARD_RECONCILE_S", "reconcile_poll_seconds", float),
                            ("FLOWGUARD_EVENT_ENDPOINT", "event_endpoint", str)):
        val = os.environ.get(env)
        if val is None:
            continue
        if attr is None:  # data dir override relocates every runtime path
            base = os.path.abspath(val)
            cfg.db_path, cfg.spool_path = f"{base}/engine/golden.db", f"{base}/spool/alerts.jsonl"
            cfg.eventlog_path, cfg.run_dir = f"{base}/run/engine_events.jsonl", f"{base}/run"
            if "FLOWGUARD_EVENT_ENDPOINT" not in os.environ:
                cfg.event_endpoint = f"ipc://{base}/run/events.ipc"
        else:
            setattr(cfg, attr, cast(val))
    if cfg.response_mode not in ("restore", "alert_only"):
        raise ValueError("response_mode must be restore or alert_only")
    if cfg.verify_mode not in ("event", "poll"):
        raise ValueError("verify_mode must be event or poll")
    return cfg.resolved()
