"""Policies, recorded sessions, reports, audit log, engine control, health."""
from __future__ import annotations

import csv
import io
import json
import os
import statistics
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import audit
from ..deps import Principal, admin, analyst, audit_event, get_db, viewer
from ..models import Alert, AuditEvent, Incident, Meta, PolicyDoc, PolicyHistory, Recording, RuleSnapshot, Switch

router = APIRouter(prefix="/api", tags=["admin"])

# ---- policies ----------------------------------------------------------------------------------------------------
Action = Literal["restore_and_alert", "quarantine_port", "alert_only", "none"]


class RiskWeights(BaseModel):
    l1: float = Field(ge=0, le=1)
    l2: float = Field(ge=0, le=1)
    l3: float = Field(ge=0, le=1)


class RiskThresholds(BaseModel):
    alert: float = Field(ge=0, le=1)
    restore: float = Field(ge=0, le=1)
    quarantine: float = Field(ge=0, le=1)

    @field_validator("quarantine")
    @classmethod
    def ordered(cls, v: float, info: Any) -> float:
        d = info.data
        if "alert" in d and "restore" in d and not d["alert"] <= d["restore"] <= v:
            raise ValueError("thresholds must satisfy alert <= restore <= quarantine")
        return v


class PolicyIn(BaseModel):
    dry_run: bool
    response_mode: Literal["restore", "alert_only"]
    critical_tables: List[int] = Field(min_length=1, max_length=16)
    weights: RiskWeights
    thresholds: RiskThresholds
    actions: Dict[Literal["critical", "high", "medium", "low"], Action]

    @field_validator("critical_tables")
    @classmethod
    def tables_in_range(cls, v: List[int]) -> List[int]:
        if any(t < 0 or t > 254 for t in v) or len(set(v)) != len(v):
            raise ValueError("critical_tables must be unique table ids in 0..254")
        return sorted(v)


DEFAULT_POLICY: Dict[str, Any] = {
    "dry_run": True, "response_mode": "restore", "critical_tables": [0],
    "weights": {"l1": 1.0, "l2": 0.8, "l3": 0.4}, "thresholds": {"alert": 0.3, "restore": 0.5, "quarantine": 0.8},
    "actions": {"critical": "restore_and_alert", "high": "restore_and_alert", "medium": "alert_only", "low": "alert_only"},
}
# Honest flag shown with every policy read: the engine does not read this document yet (it uses config.yaml);
# the risk engine that enforces it arrives in Phase 5.
ENFORCED = False


def ensure_policy(db: Session) -> PolicyDoc:
    doc = db.get(PolicyDoc, 1)
    if doc is None:
        doc = PolicyDoc(id=1, version=1, data=json.dumps(DEFAULT_POLICY, sort_keys=True), updated_at=time.time(), updated_by=None)
        db.add(doc)
        db.add(PolicyHistory(version=1, data=doc.data, t=doc.updated_at, username=None))
        db.commit()
    return doc


@router.get("/policies")
def get_policy(p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    doc = ensure_policy(db)
    return {"version": doc.version, "updated_at": doc.updated_at, "updated_by": doc.updated_by, "enforced": ENFORCED,
            "policy": json.loads(doc.data)}


@router.put("/policies")
def put_policy(body: PolicyIn, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    doc = ensure_policy(db)
    old = json.loads(doc.data)
    new = body.model_dump()
    doc.version += 1
    doc.data, doc.updated_at, doc.updated_by = json.dumps(new, sort_keys=True), time.time(), p.username
    db.add(PolicyHistory(version=doc.version, data=doc.data, t=doc.updated_at, username=p.username))
    db.commit()
    changed = sorted(k for k in new if new[k] != old.get(k))
    audit_event(request, db, "policy_updated", p, target=f"v{doc.version}", details={"changed": changed})
    return {"version": doc.version, "updated_at": doc.updated_at, "updated_by": doc.updated_by, "enforced": ENFORCED, "policy": new}


@router.get("/policies/history")
def policy_history(p: Principal = Depends(analyst), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    ensure_policy(db)
    return [{"version": h.version, "t": h.t, "username": h.username, "policy": json.loads(h.data)}
            for h in db.execute(select(PolicyHistory).order_by(PolicyHistory.version.desc())).scalars()]


# ---- recorded sessions -----------------------------------------------------------------------------------------
class RecordingIn(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9 _.,:()-]+$")


def _rec_out(r: Recording, live_id: Optional[str]) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "started_at": r.started_at, "stopped_at": r.stopped_at, "started_by": r.started_by,
            "records": r.records, "recording": r.id == live_id}


@router.get("/sessions")
def list_sessions(request: Request, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    live = request.app.state.ingestor.recording_id
    return [_rec_out(r, live) for r in db.execute(select(Recording).order_by(Recording.started_at.desc())).scalars()]


@router.post("/sessions", status_code=201)
def start_session(body: RecordingIn, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    ing = request.app.state.ingestor
    if ing.recording_id:
        raise HTTPException(status_code=409, detail="a recording is already running")
    rid = uuid.uuid4().hex
    path = os.path.join(request.app.state.settings.sessions_dir, f"{rid}.jsonl")  # never derived from user input
    r = Recording(id=rid, name=body.name, started_at=time.time(), started_by=p.username, path=path, records=0)
    db.add(r)
    db.commit()
    ing.start_recording(rid, path)
    audit_event(request, db, "recording_started", p, target=rid, details={"name": body.name})
    return _rec_out(r, rid)


@router.post("/sessions/{rec_id}/stop")
def stop_session(rec_id: str, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    ing = request.app.state.ingestor
    r = db.get(Recording, rec_id)
    if r is None:
        raise HTTPException(status_code=404, detail="unknown recording")
    if ing.recording_id != rec_id:
        raise HTTPException(status_code=409, detail="this recording is not running")
    _, n = ing.stop_recording()  # type: ignore[misc]
    r.stopped_at, r.records = time.time(), n
    db.commit()
    audit_event(request, db, "recording_stopped", p, target=rec_id, details={"records": n})
    return _rec_out(r, None)


@router.get("/sessions/{rec_id}/download")
def download_session(rec_id: str, request: Request, p: Principal = Depends(analyst), db: Session = Depends(get_db)):
    r = db.get(Recording, rec_id)
    if r is None or not os.path.exists(r.path):
        raise HTTPException(status_code=404, detail="unknown recording or no records yet")
    audit_event(request, db, "recording_exported", p, target=rec_id)
    return FileResponse(r.path, media_type="application/x-ndjson", filename=f"flowguard-session-{rec_id}.jsonl")


# ---- reports ---------------------------------------------------------------------------------------------------
def _stats(values: List[float]) -> Optional[Dict[str, Any]]:
    if not values:
        return None
    vs = sorted(values)
    p95 = vs[min(len(vs) - 1, int(round(0.95 * (len(vs) - 1))))]
    return {"n": len(vs), "mean": round(statistics.fmean(vs), 2), "median": round(statistics.median(vs), 2), "p95": round(p95, 2)}


@router.get("/reports/summary")
def report_summary(p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Computed only from stored alerts; empty sections are null, never invented."""
    by_kind = dict(db.execute(select(Alert.kind, func.count()).group_by(Alert.kind)).all())
    by_sev = dict(db.execute(select(Alert.severity, func.count()).group_by(Alert.severity)).all())
    detect = [v for (v,) in db.execute(select(Alert.detect_latency_ms).where(Alert.detect_latency_ms.is_not(None))).all()]
    restore = [v for (v,) in db.execute(select(Alert.time_to_restore_ms).where(Alert.time_to_restore_ms.is_not(None))).all()]
    open_inc = db.execute(select(func.count(Incident.id)).where(Incident.status != "closed")).scalar()
    return {"generated_at": time.time(), "source": "core database (alerts ingested from the engine)",
            "alerts_total": sum(by_kind.values()), "alerts_by_kind": by_kind, "alerts_by_severity": by_sev,
            "open_incidents": open_inc, "detect_latency_ms": _stats(detect), "time_to_restore_ms": _stats(restore),
            "note": "engine-side latencies (monitor event to classification); one entry per alert"}


def _csv_safe(v: Any) -> Any:
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ (or tab/CR) gets a leading quote."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


@router.get("/reports/alerts.csv")
def report_alerts_csv(request: Request, p: Principal = Depends(analyst), db: Session = Depends(get_db)) -> StreamingResponse:
    cols = ["id", "t", "kind", "severity", "layer", "dpid", "table_id", "priority", "action", "detected_by",
            "detect_latency_ms", "time_to_restore_ms", "status", "incident_id", "summary"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for a in db.execute(select(Alert).order_by(Alert.t)).scalars():
        w.writerow([_csv_safe(getattr(a, c)) for c in cols])
    audit_event(request, db, "report_exported", p, target="alerts.csv")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="flowguard-alerts.csv"'})


# ---- audit log -----------------------------------------------------------------------------------------------------
@router.get("/audit")
def audit_list(action: Optional[str] = None, username: Optional[str] = None, result: Optional[str] = None,
               limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0),
               p: Principal = Depends(analyst), db: Session = Depends(get_db)) -> Dict[str, Any]:
    q = select(AuditEvent)
    for col, val in ((AuditEvent.action, action), (AuditEvent.username, username), (AuditEvent.result, result)):
        if val is not None:
            q = q.where(col == val)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    items = [{"id": e.id, "t": e.t, "username": e.username, "role": e.role, "action": e.action, "target": e.target,
              "result": e.result, "ip": e.ip, "user_agent": e.user_agent, "details": json.loads(e.details), "hash": e.hash}
             for e in db.execute(q.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).scalars()]
    return {"total": total, "items": items}


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    ok, bad, n = audit.verify_chain(db)
    return {"ok": ok, "first_bad_id": bad, "rows_checked": n}


# ---- engine control + health -----------------------------------------------------------------------------------
def _engine_status(db: Session) -> Dict[str, Any]:
    row = db.get(Meta, "engine_status")
    got = db.get(Meta, "engine_status_received_at")
    if row is None:
        return {"known": False}
    st = json.loads(row.value)
    age = time.time() - float(got.value) if got else None
    return {"known": True, "age_seconds": round(age, 1) if age is not None else None, "stale": age is None or age > 15,
            "status": st}


@router.get("/engine/status")
def engine_status(p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _engine_status(db)


@router.post("/engine/rotate-key", status_code=202)
def rotate_key(request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Ask the engine to start a new key epoch (it watches a control file). The response only confirms the request."""
    d = request.app.state.settings.control_dir
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "rotate"), "w") as fh:
        fh.write(str(time.time()))
    audit_event(request, db, "key_rotation_requested", p)
    return {"requested": True, "note": "the engine picks this up within about a second; watch engine events for key_rotated"}


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Public liveness check: no details."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/health/detail")
def health_detail(request: Request, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    app = request.app
    rcv = getattr(app.state, "receiver", None)
    tail = getattr(app.state, "tail", None)
    eng = _engine_status(db)
    engine_seq = None
    if eng.get("known"):
        engine_seq = eng["status"].get("spool", {}).get("acked")
    return {
        "database": "ok",
        "receiver": rcv.status if rcv else {"running": False},
        "ingest": app.state.ingestor.stats,
        "spool": {"ingested_seq": tail.last_seq if tail else None},
        "websocket": {"clients": app.state.hub.clients, "dropped_total": app.state.hub.dropped_total},
        "engine": eng,
        "switches": db.execute(select(func.count(Switch.dpid))).scalar(),
        "snapshots": db.execute(select(func.count(RuleSnapshot.id))).scalar(),
        "engine_reported_ack": engine_seq,
    }
