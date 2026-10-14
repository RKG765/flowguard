"""Hash-chained audit log. Each row stores sha256(prev_hash + canonical row), so editing or deleting a row in the
middle of the table is detectable with ``verify_chain`` (it does not stop someone with database write access from
rewriting the whole chain; that limit is documented in the security review)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent

GENESIS = "0" * 64
_chain_lock = threading.Lock()


def _canonical(e: AuditEvent) -> str:
    body = {"t": round(e.t, 6), "user_id": e.user_id, "username": e.username, "role": e.role, "action": e.action,
            "target": e.target, "result": e.result, "ip": e.ip, "user_agent": e.user_agent, "details": e.details}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _hash(prev: str, e: AuditEvent) -> str:
    return hashlib.sha256((prev + _canonical(e)).encode("utf-8")).hexdigest()


def _sanitize(value: Optional[str], limit: int) -> Optional[str]:
    """Strip control characters (no log injection through usernames, user agents, targets) and bound the length."""
    if value is None:
        return None
    cleaned = "".join(ch if ch.isprintable() else "?" for ch in str(value))
    return cleaned[:limit]


def record(db: Session, action: str, *, result: str = "success", actor: Optional[Dict[str, Any]] = None,
           target: Optional[str] = None, details: Optional[Dict[str, Any]] = None, ip: Optional[str] = None,
           user_agent: Optional[str] = None, commit: bool = True) -> AuditEvent:
    """Append one audit row. ``actor`` is {"id", "username", "role"} or None for anonymous actions."""
    with _chain_lock:
        last = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar()
        e = AuditEvent(
            t=time.time(), user_id=(actor or {}).get("id"), username=_sanitize((actor or {}).get("username"), 64),
            role=(actor or {}).get("role"), action=action, target=_sanitize(target, 255), result=result,
            ip=_sanitize(ip, 64), user_agent=_sanitize(user_agent, 255),
            details=json.dumps(details or {}, sort_keys=True, default=str), prev_hash=last or GENESIS, hash="")
        e.hash = _hash(e.prev_hash, e)
        db.add(e)
        if commit:
            db.commit()
        else:
            db.flush()
        return e


def verify_chain(db: Session) -> Tuple[bool, Optional[int], int]:
    """Return (ok, first_bad_id, rows_checked)."""
    prev = GENESIS
    n = 0
    for e in db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        n += 1
        if e.prev_hash != prev or _hash(prev, e) != e.hash:
            return False, e.id, n
        prev = e.hash
    return True, None, n
