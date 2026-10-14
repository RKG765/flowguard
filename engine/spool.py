"""Durable alert spool (ADR-009): alerts are appended and fsynced here BEFORE they are sent to the core.

Rotation: when a file would exceed ``max_bytes`` it is renamed to ``.1`` (older files shift up). At most
``backups`` rotated files are kept; when the oldest is dropped, the records in it that were never acknowledged
are counted in ``dropped_total`` and ``append`` reports the overflow so the caller can raise a visible alert.
Acknowledgement is a monotonically increasing sequence number kept in ``<path>.ack``.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class AppendResult:
    seq: int
    overflowed: bool
    dropped: int  # unacknowledged records lost by this append's rotation (0 when no overflow)


class AlertSpool:
    def __init__(self, path: str, max_bytes: int = 10 * 1024 * 1024, backups: int = 5) -> None:
        if max_bytes < 1024 or backups < 1:
            raise ValueError("max_bytes must be >= 1024 and backups >= 1")
        self.path, self.max_bytes, self.backups = path, max_bytes, backups
        self.dropped_total = 0
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._heal_tail()
        self._seq = self._recover_last_seq()

    def _heal_tail(self) -> None:
        """A crash can leave a half-written last line. Terminate it so the next record starts on its own line."""
        try:
            with open(self.path, "rb+") as fh:
                fh.seek(0, os.SEEK_END)
                if fh.tell() > 0:
                    fh.seek(-1, os.SEEK_END)
                    if fh.read(1) != b"\n":
                        fh.write(b"\n")
                        fh.flush()
                        os.fsync(fh.fileno())
        except FileNotFoundError:
            pass

    # ---- files ---------------------------------------------------------------------------------------------
    def _file(self, n: int) -> str:
        return self.path if n == 0 else f"{self.path}.{n}"

    def _files_oldest_first(self) -> List[str]:
        return [self._file(n) for n in range(self.backups, -1, -1) if os.path.exists(self._file(n))]

    @property
    def ack_path(self) -> str:
        return self.path + ".ack"

    def _recover_last_seq(self) -> int:
        last = self.acked()
        for rec in self._iter_records():
            last = max(last, int(rec.get("seq", 0)))
        return last

    def _iter_records(self) -> Iterator[Dict[str, Any]]:
        for fname in self._files_oldest_first():
            with open(fname, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue  # a torn last line after a crash must not block recovery

    # ---- API -----------------------------------------------------------------------------------------------
    def append(self, record: Dict[str, Any]) -> AppendResult:
        with self._lock:
            self._seq += 1
            rec = dict(record, seq=self._seq)
            data = (json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            dropped = 0
            if os.path.exists(self.path) and os.path.getsize(self.path) + len(data) > self.max_bytes:
                dropped = self._rotate()
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            return AppendResult(self._seq, dropped > 0, dropped)

    def _rotate(self) -> int:
        oldest = self._file(self.backups)
        dropped = 0
        if os.path.exists(oldest):
            acked = self.acked()
            with open(oldest, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        if int(json.loads(line).get("seq", 0)) > acked:
                            dropped += 1
                    except ValueError:
                        pass
            os.remove(oldest)
        for n in range(self.backups - 1, -1, -1):
            if os.path.exists(self._file(n)):
                os.replace(self._file(n), self._file(n + 1))
        self.dropped_total += dropped
        return dropped

    def ack(self, seq: int) -> None:
        """Record that the core has stored every alert up to and including ``seq`` (never moves backwards)."""
        with self._lock:
            if seq <= self.acked():
                return
            tmp = self.ack_path + ".tmp"
            with open(tmp, "w", encoding="ascii") as fh:
                fh.write(str(seq))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.ack_path)

    def acked(self) -> int:
        try:
            with open(self.ack_path, "r", encoding="ascii") as fh:
                return int(fh.read().strip() or 0)
        except (FileNotFoundError, ValueError):
            return 0

    def unacked(self) -> List[Dict[str, Any]]:
        """Records the core has not acknowledged, oldest first (replayed after a core outage or restart)."""
        with self._lock:
            acked = self.acked()
            return [r for r in self._iter_records() if int(r.get("seq", 0)) > acked]

    def total_bytes(self) -> int:
        return sum(os.path.getsize(f) for f in self._files_oldest_first())
