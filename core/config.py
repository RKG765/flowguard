"""Core service settings: defaults, FLOWGUARD_* environment overrides. Paths are shared with the engine's data dir."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CoreSettings:
    data_dir: str = str(REPO / "data")
    bind_host: str = "127.0.0.1"
    port: int = 8787
    session_ttl_hours: float = 12.0
    login_max_failures: int = 5
    login_window_seconds: float = 300.0
    login_lockout_seconds: float = 60.0
    ws_ticket_seconds: float = 30.0
    cookie_secure: bool = False          # the dashboard is served over http://localhost; set True behind TLS
    events_keep: int = 5000              # newest engine events kept in the database
    incident_group_seconds: float = 1800.0
    spool_poll_seconds: float = 1.0
    start_receiver: bool = True          # tests turn the ZeroMQ/spool ingest thread off
    event_endpoint: str = ""             # default: ipc://<data_dir>/run/events.ipc (the engine connects here)

    # ---- derived paths ----------------------------------------------------------------------------------------
    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "core", "core.db")

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def spool_path(self) -> str:
        return os.path.join(self.data_dir, "spool", "alerts.jsonl")

    @property
    def engine_status_path(self) -> str:
        return os.path.join(self.data_dir, "run", "engine_status.json")

    @property
    def control_dir(self) -> str:
        return os.path.join(self.data_dir, "run", "control")

    @property
    def sessions_dir(self) -> str:
        return os.path.join(self.data_dir, "sessions")

    @property
    def endpoint(self) -> str:
        return self.event_endpoint or f"ipc://{os.path.join(self.data_dir, 'run', 'events.ipc')}"


def load_settings(**overrides: object) -> CoreSettings:
    s = CoreSettings()
    env = os.environ
    if env.get("FLOWGUARD_DATA_DIR"):
        s = replace(s, data_dir=os.path.abspath(env["FLOWGUARD_DATA_DIR"]))
    if env.get("FLOWGUARD_EVENT_ENDPOINT"):
        s = replace(s, event_endpoint=env["FLOWGUARD_EVENT_ENDPOINT"])
    if env.get("FLOWGUARD_BIND_HOST"):
        s = replace(s, bind_host=env["FLOWGUARD_BIND_HOST"])
    if env.get("FLOWGUARD_PORT"):
        s = replace(s, port=int(env["FLOWGUARD_PORT"]))
    if env.get("FLOWGUARD_COOKIE_SECURE"):
        s = replace(s, cookie_secure=env["FLOWGUARD_COOKIE_SECURE"] == "1")
    return replace(s, **overrides)  # type: ignore[arg-type]
