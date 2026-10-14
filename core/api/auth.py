"""First-run setup, login/logout, current user, WebSocket tickets, user management."""
from __future__ import annotations

import time
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..deps import COOKIE_NAME, Principal, admin, audit_event, client_ip, get_db, resolve_principal, user_agent, viewer
from ..models import AuthSession, User
from ..security import hash_password, new_token, password_problem, token_hash, verify_password

router = APIRouter(prefix="/api", tags=["auth"])
Role = Literal["viewer", "analyst", "admin"]
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,64}$"


class Credentials(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class NewUser(Credentials):
    role: Role


class UserPatch(BaseModel):
    role: Optional[Role] = None
    disabled: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=1, max_length=256)


def _user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "disabled": u.disabled, "created_at": u.created_at,
            "last_login": u.last_login}


def _check_password(username: str, password: str) -> None:
    problem = password_problem(username, password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


# ---- first-run setup ----------------------------------------------------------------------------------------
@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)) -> dict:
    return {"needs_setup": db.execute(select(func.count(User.id))).scalar() == 0}


@router.post("/setup", status_code=201)
def setup(body: Credentials, request: Request, db: Session = Depends(get_db)) -> dict:
    """Create the first admin. Only works while there are no users at all."""
    if db.execute(select(func.count(User.id))).scalar() != 0:
        audit_event(request, db, "setup_rejected", result="denied", target=body.username)
        raise HTTPException(status_code=409, detail="setup already done")
    _check_password(body.username, body.password)
    u = User(username=body.username, password_hash=hash_password(body.password), role="admin", created_at=time.time())
    db.add(u)
    db.commit()
    audit_event(request, db, "setup_admin_created", None, target=u.username, details={"user_id": u.id})
    return _user_out(u)


# ---- sessions -------------------------------------------------------------------------------------------------
@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    s = request.app.state.settings
    limiter = request.app.state.login_limiter
    ip = client_ip(request) or "?"
    wait = limiter.locked_for(ip, body.username)
    if wait > 0:
        audit_event(request, db, "login_locked", result="denied", target=body.username)
        raise HTTPException(status_code=429, detail="too many failed logins; try again later",
                            headers={"Retry-After": str(int(wait) + 1)})
    u = db.execute(select(User).where(User.username == body.username)).scalar()
    if not verify_password(u.password_hash if u else None, body.password) or u is None or u.disabled:
        limiter.failure(ip, body.username)
        audit_event(request, db, "login_failed", result="failed", target=body.username)
        raise HTTPException(status_code=401, detail="invalid username or password")
    limiter.success(ip, body.username)
    token, csrf = new_token(), new_token()
    now = time.time()
    expires = now + s.session_ttl_hours * 3600
    db.add(AuthSession(token_hash=token_hash(token), csrf_token=csrf, user_id=u.id, created_at=now, expires_at=expires,
                       ip=ip, user_agent=(user_agent(request) or "")[:255]))
    u.last_login = now
    db.commit()
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", secure=s.cookie_secure, path="/",
                        max_age=int(s.session_ttl_hours * 3600))
    audit_event(request, db, "login", Principal(u.id, u.username, u.role, 0, "", "cookie"))
    return {"token": token, "csrf_token": csrf, "expires_at": expires, "user": _user_out(u)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, p: Principal = Depends(viewer), db: Session = Depends(get_db)) -> dict:
    db.execute(update(AuthSession).where(AuthSession.id == p.session_id).values(revoked=True))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    audit_event(request, db, "logout", p)
    return {"ok": True}


@router.get("/auth/me")
def me(p: Principal = Depends(viewer)) -> dict:
    return {"id": p.id, "username": p.username, "role": p.role, "csrf_token": p.csrf_token}


@router.post("/auth/ws-ticket")
def ws_ticket(request: Request, p: Principal = Depends(viewer)) -> dict:
    return {"ticket": request.app.state.tickets.issue({"id": p.id, "username": p.username, "role": p.role}),
            "expires_in": request.app.state.settings.ws_ticket_seconds}


# ---- users (admin) -----------------------------------------------------------------------------------------------
@router.get("/users")
def list_users(p: Principal = Depends(admin), db: Session = Depends(get_db)) -> List[dict]:
    return [_user_out(u) for u in db.execute(select(User).order_by(User.id)).scalars()]


@router.post("/users", status_code=201)
def create_user(body: NewUser, request: Request, p: Principal = Depends(admin), db: Session = Depends(get_db)) -> dict:
    if db.execute(select(User).where(User.username == body.username)).scalar():
        raise HTTPException(status_code=409, detail="username already exists")
    _check_password(body.username, body.password)
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role, created_at=time.time())
    db.add(u)
    db.commit()
    audit_event(request, db, "user_created", p, target=u.username, details={"role": u.role})
    return _user_out(u)


def _active_admins(db: Session) -> int:
    return int(db.execute(select(func.count(User.id)).where(User.role == "admin", User.disabled.is_(False))).scalar() or 0)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, request: Request, p: Principal = Depends(admin),
               db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="no such user")
    losing_admin = u.role == "admin" and not u.disabled and ((body.role not in (None, "admin")) or body.disabled is True)
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="cannot remove or disable the last active admin")
    changes = {}
    if body.role is not None and body.role != u.role:
        changes["role"] = [u.role, body.role]
        u.role = body.role
    if body.disabled is not None and body.disabled != u.disabled:
        changes["disabled"] = [u.disabled, body.disabled]
        u.disabled = body.disabled
    if body.password is not None:
        _check_password(u.username, body.password)
        u.password_hash = hash_password(body.password)
        changes["password"] = "changed"
    if changes:  # any change to role, status or password ends the user's existing sessions
        db.execute(update(AuthSession).where(AuthSession.user_id == u.id).values(revoked=True))
    db.commit()
    audit_event(request, db, "user_updated", p, target=u.username, details=changes)
    return _user_out(u)
