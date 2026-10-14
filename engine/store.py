"""Golden store: the signed rules the controller intends every switch to hold (SQLite, WAL).

Keyed by (dpid, table_id, priority, canonical match). Cookies are stored as 16-digit hex text because SQLite
integers are signed 64-bit and a cookie can use all 64 bits. All installs go through the engine's
``install_signed_rule`` which writes here first, so the store is never behind the switch.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .canonical import RuleSpec, dpid_hex
from .crypto import EpochPolicy

SCHEMA = """
CREATE TABLE IF NOT EXISTS golden_rules (
  dpid TEXT NOT NULL, table_id INTEGER NOT NULL, priority INTEGER NOT NULL, match_key TEXT NOT NULL,
  spec_json TEXT NOT NULL, epoch INTEGER NOT NULL, cookie TEXT NOT NULL, installed_at REAL NOT NULL,
  PRIMARY KEY (dpid, table_id, priority, match_key)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class StoreCorrupt(Exception):
    """The database file is unreadable or fails its integrity check. The engine must alert and refuse to guess."""


@dataclass(frozen=True)
class GoldenRule:
    dpid: str  # 16 hex digits
    spec: RuleSpec
    epoch: int
    cookie: int
    installed_at: float


class GoldenStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        try:
            self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript(SCHEMA)
        except sqlite3.DatabaseError as exc:
            raise StoreCorrupt(f"{path}: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def integrity_check(self) -> bool:
        with self._lock:
            try:
                return self._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            except sqlite3.DatabaseError:
                return False

    # ---- rules ---------------------------------------------------------------------------------------------
    def put(self, dpid: object, spec: RuleSpec, epoch: int, cookie: int, now: Optional[float] = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO golden_rules VALUES (?,?,?,?,?,?,?,?)",
                (dpid_hex(dpid), spec.table_id, spec.priority, spec.match_key(), json.dumps(spec.to_dict(), sort_keys=True),
                 epoch, f"{cookie:016x}", time.time() if now is None else now))

    def get(self, dpid: object, spec: RuleSpec) -> Optional[GoldenRule]:
        with self._lock:
            row = self._db.execute(
                "SELECT dpid, spec_json, epoch, cookie, installed_at FROM golden_rules "
                "WHERE dpid=? AND table_id=? AND priority=? AND match_key=?",
                (dpid_hex(dpid), spec.table_id, spec.priority, spec.match_key())).fetchone()
        return self._row(row) if row else None

    def delete(self, dpid: object, spec: RuleSpec) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM golden_rules WHERE dpid=? AND table_id=? AND priority=? AND match_key=?",
                                   (dpid_hex(dpid), spec.table_id, spec.priority, spec.match_key()))
            return cur.rowcount > 0

    def list(self, dpid: object, table_id: Optional[int] = None) -> List[GoldenRule]:
        q, args = "SELECT dpid, spec_json, epoch, cookie, installed_at FROM golden_rules WHERE dpid=?", [dpid_hex(dpid)]
        if table_id is not None:
            q, args = q + " AND table_id=?", args + [table_id]
        with self._lock:
            rows = self._db.execute(q + " ORDER BY table_id, priority DESC, match_key", args).fetchall()
        return [self._row(r) for r in rows]

    def dpids(self) -> List[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT DISTINCT dpid FROM golden_rules ORDER BY dpid")]

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM golden_rules").fetchone()[0])

    @staticmethod
    def _row(row: tuple) -> GoldenRule:
        dpid, spec_json, epoch, cookie, installed_at = row
        return GoldenRule(dpid, RuleSpec.from_dict(json.loads(spec_json)), int(epoch), int(cookie, 16), float(installed_at))

    # ---- epoch policy persistence (so a restart does not forget a rotation) ---------------------------------
    def save_epoch_policy(self, policy: EpochPolicy) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO meta VALUES ('epoch_policy', ?)", (json.dumps(policy.to_dict()),))

    def load_epoch_policy(self, grace_seconds: Optional[float] = None) -> Optional[EpochPolicy]:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key='epoch_policy'").fetchone()
        return EpochPolicy.from_dict(json.loads(row[0]), grace_seconds) if row else None

    def meta_summary(self) -> Dict[str, object]:
        return {"path": self.path, "rules": self.count(), "dpids": self.dpids()}
