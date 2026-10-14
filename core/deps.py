"""Request dependencies: database session, the authenticated principal, role checks, CSRF, audit helper.

Authentication: the session token comes from the HttpOnly cookie ``fg_session`` (browser) or an
``Authorization: Bearer`` header (API clients, tests). Cookie-authenticated state-changing requests must carry the
session's CSRF token in ``X-CSRF-Token`` (double-submit is not used: the token is bound to the server-side session).
Every denial (401 excluded) is written to the audit log.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .models import AuthSession, User
from .security import token_hash

ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
COOKIE_NAME = "fg_session"


@dataclass(frozen=True)
class Principal:
    id: int
    username: str
    role: str
    session_id: int
    csrf_token: str
    via: str  # cookie | bearer

    def actor(self) -> Dict[str, Any]:
        return {"id": self.id, "username": self.username, "role": self.role}


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.sf()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent")


def _token_from(request: Request) -> Optional[tuple]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), "bearer"
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie, "cookie"
    return None


def resolve_principal(request: Request, db: Session) -> Optional[Principal]:
    found = _token_from(request)
    if not found:
        return None
    token, via = found
    now = time.time()
    row = db.execute(select(AuthSession, User).join(User, AuthSession.user_id == User.id)
                     .where(AuthSession.token_hash == token_hash(token))).first()
    if row is None:
        return None
    sess, user = row
    if sess.revoked or sess.expires_at < now or user.disabled:
        return None
    return Principal(user.id, user.username, user.role, sess.id, sess.csrf_token, via)


def audit_event(request: Request, db: Session, action: str, principal: Optional[Principal] = None, *,
                result: str = "success", target: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
    audit.record(db, action, result=result, actor=principal.actor() if principal else None, target=target,
                 details=details, ip=client_ip(request), user_agent=user_agent(request))


def require(min_role: str) -> Callable[..., Principal]:
    """Dependency factory: authenticated user with at least ``min_role``; CSRF enforced for cookie sessions."""
    if min_role not in ROLE_RANK:
        raise ValueError(min_role)

    def dep(request: Request, db: Session = Depends(get_db)) -> Principal:
        p = resolve_principal(request, db)
        if p is None:
            raise HTTPException(status_code=401, detail="authentication required")
        target = f"{request.method} {request.url.path}"
        if ROLE_RANK.get(p.role, -1) < ROLE_RANK[min_role]:
            audit_event(request, db, "permission_denied", p, result="denied", target=target,
                        details={"required_role": min_role})
            raise HTTPException(status_code=403, detail=f"requires role {min_role}")
        if p.via == "cookie" and request.method not in SAFE_METHODS and request.headers.get("x-csrf-token") != p.csrf_token:
            audit_event(request, db, "csrf_rejected", p, result="denied", target=target)
            raise HTTPException(status_code=403, detail="CSRF token missing or wrong")
        request.state.principal = p
        return p

    dep.__name__ = f"require_{min_role}"
    return dep


viewer = require("viewer")
analyst = require("analyst")
admin = require("admin")
