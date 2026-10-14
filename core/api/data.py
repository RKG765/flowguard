"""Read APIs for switches, rules (with integrity status), alerts, incidents, engine events, probes and ML scores,
plus the analyst actions on alerts and incidents."""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Principal, admin, analyst, audit_event, get_db, viewer
from ..models import Alert, EngineEvent, Incident, IncidentNote, MlScore, ProbeResult, RuleSnapshot, Switch

router = APIRouter(prefix="/api", tags=["data"])
RULE_STATUSES = ("ok", "altered", "shadow", "forged", "missing", "pending")


def alert_out(a: Alert, full: bool = False) -> Dict[str, Any]:
    out = {"id": a.id, "seq": a.seq, "t": a.t, "kind": a.kind, "severity": a.severity, "layer": a.layer, "dpid": a.dpid,
           "table_id": a.table_id, "priority": a.priority, "action": a.action, "detected_by": a.detected_by,
           "summary": a.summary, "detect_latency_ms": a.detect_latency_ms, "time_to_restore_ms": a.time_to_restore_ms,
           "restored_at": a.restored_at, "status": a.status, "acknowledged_by": a.acknowledged_by,
           "acknowledged_at": a.acknowledged_at, "incident_id": a.incident_id}
    if full:
        out["details"] = json.loads(a.payload)
    return out


def incident_out(i: Incident) -> Dict[str, Any]:
    return {"id": i.id, "title": i.title, "severity": i.severity, "status": i.status, "dpid": i.dpid,
            "assignee": i.assignee, "alert_count": i.alert_count, "created_at": i.created_at, "updated_at": i.updated_at,
            "closed_at": i.closed_at}


# ---- switches -------------------------------------------------------------------------------------------------
@router.get("/switches")
def switches(p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    out = []
    for sw in db.execute(select(Switch).order_by(Switch.dpid)).scalars():
        out.append({"dpid": sw.dpid, "name": sw.name, "connected": sw.connected, "monitor_up": sw.monitor_up,
                    "first_seen": sw.first_seen, "last_seen": sw.last_seen,
                    "open_incidents": db.execute(select(func.count(Incident.id)).where(Incident.dpid == sw.dpid,
                                                                                      Incident.status != "closed")).scalar()})
    return out


@router.get("/switches/{dpid}")
def switch_detail(dpid: str, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    sw = db.get(Switch, dpid)
    if sw is None:
        raise HTTPException(status_code=404, detail="unknown switch")
    recent = db.execute(select(Alert).where(Alert.dpid == dpid).order_by(Alert.t.desc()).limit(20)).scalars()
    return {"dpid": sw.dpid, "name": sw.name, "connected": sw.connected, "monitor_up": sw.monitor_up,
            "first_seen": sw.first_seen, "last_seen": sw.last_seen, "rules": _rules(db, dpid, None, None),
            "recent_alerts": [alert_out(a) for a in recent]}


# ---- rules ------------------------------------------------------------------------------------------------------
def _rules(db: Session, dpid: Optional[str], table_id: Optional[int], status: Optional[str]) -> List[Dict[str, Any]]:
    q = select(RuleSnapshot)
    if dpid:
        q = q.where(RuleSnapshot.dpid == dpid)
    if table_id is not None:
        q = q.where(RuleSnapshot.table_id == table_id)
    out = []
    for snap in db.execute(q.order_by(RuleSnapshot.dpid, RuleSnapshot.table_id)).scalars():
        for r in json.loads(snap.rules_json):
            if status and r.get("status") != status:
                continue
            out.append(dict(r, dpid=snap.dpid, last_verified=snap.t))
    return out


@router.get("/rules")
def rules(dpid: Optional[str] = None, table_id: Optional[int] = Query(default=None, ge=0, le=254),
          status: Optional[Literal["ok", "altered", "shadow", "forged", "missing", "pending"]] = None,
          p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    return _rules(db, dpid, table_id, status)


@router.get("/rules/summary")
def rules_summary(p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = _rules(db, None, None, None)
    by_status = {s: 0 for s in RULE_STATUSES}
    for r in rows:
        by_status[r.get("status", "ok")] = by_status.get(r.get("status", "ok"), 0) + 1
    protected = [r for r in rows if r.get("golden")]
    verified = sum(1 for r in protected if r.get("status") == "ok")
    return {"rules": len(rows), "protected": len(protected), "verified": verified,
            "verified_percent": round(100.0 * verified / len(protected), 1) if protected else None, "by_status": by_status,
            "as_of": max((r["last_verified"] for r in rows), default=None)}


class RepairIn(BaseModel):
    dpid: str = Field(pattern=r"^[0-9a-f]{16}$")
    table_id: int = Field(ge=0, le=254)
    priority: int = Field(ge=0, le=65535)
    match: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("match")
    @classmethod
    def small_match(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 32:
            raise ValueError("match has too many fields")
        return v


@router.post("/rules/repair", status_code=202)
def repair_rule(body: RepairIn, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Ask the engine to repair one rule slot now (restore the signed rule, or remove an unsigned one). Only for a rule
    the latest snapshot reports as not ok. The engine acts on its next pass, even in alert_only mode."""
    rows = _rules(db, body.dpid, body.table_id, None)
    row = next((r for r in rows if r.get("priority") == body.priority and r.get("match") == body.match), None)
    if row is None:
        raise HTTPException(status_code=404, detail="no such rule in the latest snapshot of that switch")
    if row.get("status") in ("ok", "pending"):
        raise HTTPException(status_code=409, detail="the rule already matches its signed version")
    rid = uuid.uuid4().hex
    d = request.app.state.settings.control_dir
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, f"repair-{rid}.json")
    with open(final + ".tmp", "w", encoding="utf-8") as fh:  # write-then-rename: the engine never reads half a file
        json.dump({"request_id": rid, "dpid": body.dpid, "table_id": body.table_id, "priority": body.priority,
                   "match": body.match, "requested_by": p.username}, fh)
    os.replace(final + ".tmp", final)
    audit_event(request, db, "rule_repair_requested", p, target=f"{body.dpid}/t{body.table_id}/p{body.priority}",
                details={"request_id": rid, "status_before": row.get("status"), "match": body.match})
    return {"requested": True, "request_id": rid, "status_before": row.get("status")}


# ---- alerts -----------------------------------------------------------------------------------------------------
@router.get("/alerts")
def alerts(kind: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
           dpid: Optional[str] = None, since: Optional[float] = None, limit: int = Query(default=100, ge=1, le=500),
           offset: int = Query(default=0, ge=0), p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    q = select(Alert)
    for col, val in ((Alert.kind, kind), (Alert.severity, severity), (Alert.status, status), (Alert.dpid, dpid)):
        if val is not None:
            q = q.where(col == val)
    if since is not None:
        q = q.where(Alert.t >= since)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    items = db.execute(q.order_by(Alert.t.desc()).limit(limit).offset(offset)).scalars()
    return {"total": total, "items": [alert_out(a) for a in items]}


@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: str, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown alert")
    return alert_out(a, full=True)


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, request: Request, p: Principal = Depends(analyst), db: Session = Depends(get_db)) -> Dict[str, Any]:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail="unknown alert")
    if a.status != "acknowledged":
        a.status, a.acknowledged_by, a.acknowledged_at = "acknowledged", p.username, time.time()
        db.commit()
        audit_event(request, db, "alert_acknowledged", p, target=alert_id)
    return alert_out(a)


# ---- incidents ---------------------------------------------------------------------------------------------------
class IncidentPatch(BaseModel):
    status: Optional[Literal["open", "acknowledged", "closed"]] = None
    assignee: Optional[str] = Field(default=None, max_length=64)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/incidents")
def incidents(status: Optional[Literal["open", "acknowledged", "closed"]] = None, limit: int = Query(default=100, ge=1, le=500),
              offset: int = Query(default=0, ge=0), p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    q = select(Incident)
    if status:
        q = q.where(Incident.status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    items = db.execute(q.order_by(Incident.updated_at.desc()).limit(limit).offset(offset)).scalars()
    return {"total": total, "items": [incident_out(i) for i in items]}


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: int, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    i = db.get(Incident, incident_id)
    if i is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    out = incident_out(i)
    out["alerts"] = [alert_out(a) for a in db.execute(select(Alert).where(Alert.incident_id == i.id).order_by(Alert.t)).scalars()]
    out["notes"] = [{"id": n.id, "t": n.t, "username": n.username, "text": n.text}
                    for n in db.execute(select(IncidentNote).where(IncidentNote.incident_id == i.id).order_by(IncidentNote.t)).scalars()]
    return out


@router.patch("/incidents/{incident_id}")
def patch_incident(incident_id: int, body: IncidentPatch, request: Request, p: Principal = Depends(analyst),
                   db: Session = Depends(get_db)) -> Dict[str, Any]:
    i = db.get(Incident, incident_id)
    if i is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    changes: Dict[str, Any] = {}
    now = time.time()
    if body.status is not None and body.status != i.status:
        changes["status"] = [i.status, body.status]
        i.status = body.status
        i.closed_at = now if body.status == "closed" else None
    if body.assignee is not None and body.assignee != i.assignee:
        changes["assignee"] = [i.assignee, body.assignee]
        i.assignee = body.assignee or None
    if changes:
        i.updated_at = now
        db.commit()
        audit_event(request, db, "incident_updated", p, target=str(incident_id), details=changes)
    return incident_out(i)


@router.post("/incidents/{incident_id}/notes", status_code=201)
def add_note(incident_id: int, body: NoteIn, request: Request, p: Principal = Depends(analyst),
             db: Session = Depends(get_db)) -> Dict[str, Any]:
    i = db.get(Incident, incident_id)
    if i is None:
        raise HTTPException(status_code=404, detail="unknown incident")
    n = IncidentNote(incident_id=i.id, t=time.time(), username=p.username, text=body.text)
    db.add(n)
    i.updated_at = n.t
    db.commit()
    audit_event(request, db, "incident_note_added", p, target=str(incident_id), details={"note_id": n.id})
    return {"id": n.id, "t": n.t, "username": n.username, "text": n.text}


# ---- engine events, probes (L2), ML scores (L3) ------------------------------------------------------------------
@router.get("/events")
def events(limit: int = Query(default=100, ge=1, le=1000), kind: Optional[str] = None, p: Principal = Depends(viewer),
           db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    q = select(EngineEvent)
    if kind:
        q = q.where(EngineEvent.kind == kind)
    return [{"id": e.id, "t": e.t, "kind": e.kind, "dpid": e.dpid, "data": json.loads(e.payload)}
            for e in db.execute(q.order_by(EngineEvent.id.desc()).limit(limit)).scalars()]


@router.get("/probes")
def probes(limit: int = Query(default=100, ge=1, le=1000), p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    items = [{"id": r.id, "t": r.t, "dpid": r.dpid, "data": json.loads(r.payload)}
             for r in db.execute(select(ProbeResult).order_by(ProbeResult.id.desc()).limit(limit)).scalars()]
    return {"layer": "L2", "available": False, "note": "the L2 prober is planned for Phase 5", "items": items}


@router.get("/ml/scores")
def ml_scores(limit: int = Query(default=100, ge=1, le=1000), p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> Dict[str, Any]:
    items = [{"id": r.id, "t": r.t, "dpid": r.dpid, "score": r.score, "data": json.loads(r.payload)}
             for r in db.execute(select(MlScore).order_by(MlScore.id.desc()).limit(limit)).scalars()]
    return {"layer": "L3", "available": False, "note": "the L3 scorer is planned for Phase 5", "items": items}
