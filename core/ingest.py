"""Ingest records from the engine into the database and fan them out to WebSocket clients.

Two sources feed ``Ingestor.ingest``:
  * the ZeroMQ PULL socket (low latency; the engine's non-blocking PUSH)
  * ``SpoolTail``: an ordered reader of the engine's durable alert spool. It is what makes delivery reliable: alerts
    that the channel dropped, or that were written while the core was down, are picked up here, and the highest
    spool sequence processed IN ORDER is written to ``<spool>.ack`` (the acknowledgement the engine's spool reads).
Every record type is idempotent, so seeing the same alert from both sources is harmless.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from .config import CoreSettings
from .hub import Hub
from .models import Alert, EngineEvent, Incident, Meta, Recording, RuleSnapshot, Switch

log = logging.getLogger("flowguard.core.ingest")
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
OK, DUPLICATE, ERROR, IGNORED = "ok", "duplicate", "error", "ignored"


def slot_key(rec: Dict[str, Any]) -> str:
    """Incident grouping key: the rule slot for rule alerts, else switch + table + kind."""
    dpid, table = rec.get("dpid") or "global", rec.get("table_id")
    if rec.get("priority") is not None and rec.get("match") is not None:
        return f"{dpid}|{table}|{rec['priority']}|{json.dumps(rec['match'], sort_keys=True)}"
    return f"{dpid}|{table}|{rec.get('kind')}"


def incident_title(rec: Dict[str, Any]) -> str:
    kind = str(rec.get("kind", "alert")).replace("_", " ")
    where = f"switch {rec['dpid']}" if rec.get("dpid") else "FlowGuard"
    if rec.get("priority") is not None:
        return f"{kind} rule on {where}, table {rec.get('table_id')}, priority {rec['priority']}"
    if rec.get("table_id") is not None:
        return f"{kind} on {where}, table {rec['table_id']}"
    return f"{kind} on {where}"


def _meta_get(db: Session, key: str) -> Optional[str]:
    row = db.get(Meta, key)
    return row.value if row else None


def _meta_set(db: Session, key: str, value: str) -> None:
    row = db.get(Meta, key)
    if row is None:
        db.add(Meta(key=key, value=value))
    else:
        row.value = value


class Ingestor:
    def __init__(self, session_factory: sessionmaker[Session], hub: Hub, settings: CoreSettings) -> None:
        self.sf, self.hub, self.s = session_factory, hub, settings
        self._lock = threading.Lock()  # one writer: SQLite has a single write lock anyway
        self.stats: Dict[str, Any] = {"records": 0, "duplicates": 0, "errors": 0, "by_source": {}, "last_record_t": None}
        self._events_since_prune = 0
        self._recording: Optional[Tuple[str, str]] = None  # (recording id, file path)
        self._recording_count = 0

    # ---- public --------------------------------------------------------------------------------------------
    def ingest(self, rec: Dict[str, Any], source: str = "zmq") -> str:
        typ = rec.get("type")
        handler: Optional[Callable[[Session, Dict[str, Any]], bool]] = {
            "alert": self._alert, "alert_update": self._alert_update, "snapshot": self._snapshot,
            "engine_status": self._engine_status, "event": self._event}.get(str(typ))
        if handler is None:
            return IGNORED
        with self._lock:
            db = self.sf()
            try:
                new = handler(db, rec)
                db.commit()
            except Exception:  # never let one bad record kill the ingest thread
                db.rollback()
                self.stats["errors"] += 1
                log.exception("ingest failed for a %s record", typ)
                return ERROR
            finally:
                db.close()
            src = self.stats["by_source"]
            src[source] = src.get(source, 0) + 1
            self.stats["last_record_t"] = time.time()
            if not new:
                self.stats["duplicates"] += 1
                return DUPLICATE
            self.stats["records"] += 1
            self._write_recording(rec)
        self.hub.publish({"type": typ, "data": rec})
        return OK

    # ---- recorder ------------------------------------------------------------------------------------------
    def start_recording(self, rec_id: str, path: str) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._recording, self._recording_count = (rec_id, path), 0

    def stop_recording(self) -> Optional[Tuple[str, int]]:
        with self._lock:
            if self._recording is None:
                return None
            rid, n = self._recording[0], self._recording_count
            self._recording = None
            return rid, n

    @property
    def recording_id(self) -> Optional[str]:
        return self._recording[0] if self._recording else None

    def _write_recording(self, rec: Dict[str, Any]) -> None:
        if self._recording is None:
            return
        try:
            with open(self._recording[1], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"recorded_at": time.time(), "record": rec}, sort_keys=True, default=str) + "\n")
            self._recording_count += 1
        except OSError:
            log.exception("recording write failed")

    # ---- handlers (return True when something new was stored) ---------------------------------------------
    def _alert(self, db: Session, rec: Dict[str, Any]) -> bool:
        aid = str(rec.get("id") or "")
        if not aid or db.get(Alert, aid) is not None:
            return False
        seq = rec.get("seq")
        if seq is not None and db.execute(select(Alert.id).where(Alert.seq == seq)).first():
            seq = None  # a sequence collision means the engine spool was reset; keep the alert, drop the seq link
        timing = rec.get("timing") or {}
        a = Alert(id=aid, seq=seq, t=float(rec.get("t") or time.time()), kind=str(rec.get("kind", "unknown"))[:48],
                  severity=str(rec.get("severity", "medium")), layer=str(rec.get("layer", "L1")), dpid=rec.get("dpid"),
                  table_id=rec.get("table_id"), priority=rec.get("priority"), action=rec.get("action"),
                  detected_by=rec.get("detected_by"), summary=rec.get("summary"),
                  detect_latency_ms=timing.get("detect_latency_ms"), status="new",
                  payload=json.dumps(rec, sort_keys=True, default=str))
        db.add(a)
        self._attach_incident(db, a, rec)
        return True

    def _attach_incident(self, db: Session, a: Alert, rec: Dict[str, Any]) -> None:
        key = slot_key(rec)
        cutoff = a.t - self.s.incident_group_seconds
        inc = db.execute(select(Incident).where(Incident.slot_key == key, Incident.status != "closed",
                                                Incident.updated_at >= cutoff).order_by(Incident.id.desc()).limit(1)).scalar()
        if inc is None:
            inc = Incident(title=incident_title(rec), severity=a.severity, status="open", dpid=a.dpid, slot_key=key,
                           alert_count=0, created_at=a.t, updated_at=a.t)
            db.add(inc)
            db.flush()
        inc.alert_count += 1
        inc.updated_at = max(inc.updated_at, a.t)
        if SEVERITY_RANK.get(a.severity, 0) > SEVERITY_RANK.get(inc.severity, 0):
            inc.severity = a.severity
        a.incident_id = inc.id

    def _alert_update(self, db: Session, rec: Dict[str, Any]) -> bool:
        a = db.get(Alert, str(rec.get("alert_id") or ""))
        if a is None or a.restored_at is not None:
            return False
        timing = rec.get("timing") or {}
        a.restored_at = float(rec.get("t") or time.time())
        a.time_to_restore_ms = timing.get("time_to_restore_ms")
        return True

    def _snapshot(self, db: Session, rec: Dict[str, Any]) -> bool:
        dpid, table = str(rec["dpid"]), int(rec["table_id"])
        t = float(rec.get("t") or time.time())
        row = db.execute(select(RuleSnapshot).where(RuleSnapshot.dpid == dpid, RuleSnapshot.table_id == table)).scalar()
        if row is None:
            db.add(RuleSnapshot(dpid=dpid, table_id=table, t=t, epoch=rec.get("epoch"), rules_json=json.dumps(rec.get("rules", []))))
        elif t > row.t:
            row.t, row.epoch, row.rules_json = t, rec.get("epoch"), json.dumps(rec.get("rules", []))
        else:
            return False
        self._touch_switch(db, dpid, t, connected=True)
        return True

    def _engine_status(self, db: Session, rec: Dict[str, Any]) -> bool:
        t = float(rec.get("t") or time.time())
        listed = set(rec.get("switches") or [])
        monitors = rec.get("monitors_up") or {}
        for dpid in listed:
            sw = self._touch_switch(db, dpid, t, connected=True)
            sw.monitor_up = bool(monitors.get(dpid))
        for sw in db.execute(select(Switch)).scalars():
            if sw.dpid not in listed:
                sw.connected, sw.monitor_up = False, False
        _meta_set(db, "engine_status", json.dumps(rec, sort_keys=True, default=str))
        _meta_set(db, "engine_status_received_at", str(time.time()))
        return True

    def _event(self, db: Session, rec: Dict[str, Any]) -> bool:
        t = float(rec.get("t") or time.time())
        kind = str(rec.get("kind", "event"))[:48]
        dpid = rec.get("dpid")
        db.add(EngineEvent(t=t, kind=kind, dpid=dpid, payload=json.dumps(rec, sort_keys=True, default=str)))
        if dpid and kind in ("switch_connected", "switch_disconnected", "monitor_up"):
            sw = self._touch_switch(db, dpid, t, connected=kind != "switch_disconnected")
            if kind == "monitor_up":
                sw.monitor_up = True
            if kind == "switch_disconnected":
                sw.monitor_up = False
        self._events_since_prune += 1
        if self._events_since_prune >= 200:
            self._events_since_prune = 0
            cutoff = db.execute(select(EngineEvent.id).order_by(EngineEvent.id.desc()).offset(self.s.events_keep).limit(1)).scalar()
            if cutoff is not None:
                db.execute(delete(EngineEvent).where(EngineEvent.id <= cutoff))
        return True

    @staticmethod
    def _touch_switch(db: Session, dpid: str, t: float, connected: bool) -> Switch:
        sw = db.get(Switch, dpid)
        if sw is None:
            sw = Switch(dpid=dpid, first_seen=t, last_seen=t, connected=connected, monitor_up=False)
            db.add(sw)
        else:
            sw.last_seen = max(sw.last_seen, t)
            sw.connected = connected
        return sw


class SpoolTail:
    """Reads the engine's spool files oldest-first, in sequence order, from where it stopped last time."""

    def __init__(self, spool_path: str, session_factory: sessionmaker[Session]) -> None:
        self.path = spool_path
        self.sf = session_factory
        self._pos: Dict[Tuple[int, int], int] = {}
        with session_factory() as db:
            self.last_seq = int(_meta_get(db, "spool_ingested_seq") or 0)
        self.lag: Optional[int] = None

    def _files(self) -> List[str]:
        out = []
        for n in range(64, 0, -1):
            p = f"{self.path}.{n}"
            if os.path.exists(p):
                out.append(p)
        if os.path.exists(self.path):
            out.append(self.path)
        return out

    def poll(self, ingest: Callable[[Dict[str, Any], str], str]) -> int:
        """Process new complete lines. Stops at the first database error (retried next poll). Returns records seen."""
        seen = 0
        start_seq = self.last_seq
        for path in self._files():
            try:
                st = os.stat(path)
                key = (st.st_dev, st.st_ino)
                off = self._pos.get(key, 0)
                if st.st_size < off:
                    off = 0
                with open(path, "rb") as fh:
                    fh.seek(off)
                    data = fh.read()
            except OSError:
                continue
            consumed = data.rfind(b"\n") + 1  # never parse a half-written last line
            for line in data[:consumed].splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # a torn line healed by the engine
                seq = rec.get("seq")
                if not isinstance(seq, int) or seq <= self.last_seq:
                    continue
                if ingest(rec, "spool") == ERROR:
                    self._commit(start_seq)
                    return seen
                self.last_seq = seq
                seen += 1
            self._pos[key] = off + consumed
        self._commit(start_seq)
        return seen

    def _commit(self, start_seq: int) -> None:
        if self.last_seq == start_seq:
            return
        with self.sf() as db:
            _meta_set(db, "spool_ingested_seq", str(self.last_seq))
            db.commit()
        write_ack(self.path + ".ack", self.last_seq)


def write_ack(ack_path: str, seq: int) -> None:
    """Atomically write the acknowledgement, never moving it backwards."""
    try:
        with open(ack_path, "r", encoding="ascii") as fh:
            current = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        current = 0
    if seq <= current:
        return
    tmp = ack_path + ".core.tmp"
    try:
        with open(tmp, "w", encoding="ascii") as fh:
            fh.write(str(seq))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ack_path)
    except OSError:
        log.exception("could not write spool acknowledgement %s", ack_path)
