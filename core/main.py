"""FlowGuard core service app factory.

    .venv-core/bin/uvicorn --factory core.main:create_app --host 127.0.0.1 --port 8787

Binds to 127.0.0.1 by default (LAN access is an explicit opt-in via FLOWGUARD_BIND_HOST). Never runs as root by
design; in the lab the tests may run it as root only because Mininet needs root in the same process tree.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import db as dbmod
from .api import admin_api, auth, data
from .api.admin_api import ensure_policy
from .config import CoreSettings, load_settings
from .hub import Hub, TicketBook
from .ingest import Ingestor, SpoolTail
from .ipc.receiver import Receiver
from .security import LoginRateLimiter

VERSION = "0.2.0"
log = logging.getLogger("flowguard.core")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"t": round(record.created, 3), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        base.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str, sort_keys=True)


def _setup_logging() -> None:
    root = logging.getLogger("flowguard")
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_JsonFormatter())
        root.addHandler(h)
        root.setLevel(logging.INFO)
        root.propagate = False


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    s: CoreSettings = app.state.settings
    for d in (os.path.dirname(s.db_path), s.sessions_dir, s.control_dir):
        os.makedirs(d, mode=0o700, exist_ok=True)
    dbmod.upgrade(s.db_url)
    engine = dbmod.make_engine(s.db_url)
    app.state.sf = dbmod.make_session_factory(engine)
    with app.state.sf() as db:
        ensure_policy(db)
    app.state.hub.attach_loop(asyncio.get_running_loop())
    app.state.ingestor = Ingestor(app.state.sf, app.state.hub, s)
    app.state.tail = SpoolTail(s.spool_path, app.state.sf)
    app.state.receiver = None
    if s.start_receiver:
        app.state.receiver = Receiver(app.state.ingestor, s, app.state.tail)
        app.state.receiver.start()
    log.info("core_started", extra={"fields": {"version": VERSION, "db": s.db_path, "endpoint": s.endpoint}})
    try:
        yield
    finally:
        if app.state.receiver is not None:
            app.state.receiver.stop()
            app.state.receiver.join(timeout=5)
        engine.dispose()


def create_app(settings: Optional[CoreSettings] = None) -> FastAPI:
    _setup_logging()
    app = FastAPI(title="FlowGuard core API", version=VERSION, lifespan=_lifespan,
                  description="Flow-rule integrity monitoring: alerts, incidents, rules, audit. Auth: session cookie or Bearer token.")
    s = settings or load_settings()
    app.state.settings = s
    app.state.hub = Hub()
    app.state.tickets = TicketBook(s.ws_ticket_seconds)
    app.state.login_limiter = LoginRateLimiter(s.login_max_failures, s.login_window_seconds, s.login_lockout_seconds)

    @app.middleware("http")
    async def _headers_and_access_log(request: Request, call_next: Any) -> Any:
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        log.info("http", extra={"fields": {"method": request.method, "path": request.url.path, "status": response.status_code,
                                           "ms": round((time.perf_counter() - t0) * 1000, 1)}})
        return response

    app.include_router(auth.router)
    app.include_router(data.router)
    app.include_router(admin_api.router)

    @app.websocket("/api/ws")
    async def ws_stream(ws: WebSocket) -> None:
        """Live stream of alerts, alert updates, rule snapshots, engine status and events.
        Connect with ?ticket=<one-time ticket from POST /api/auth/ws-ticket>."""
        user = app.state.tickets.redeem(ws.query_params.get("ticket", ""))
        if user is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        q = app.state.hub.register()
        await ws.send_json({"type": "hello", "data": {"username": user["username"], "role": user["role"], "t": time.time()}})

        async def pump() -> None:
            while True:
                await ws.send_json(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                await ws.receive_text()  # clients do not send anything meaningful; this detects disconnects
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            app.state.hub.unregister(q)

    _mount_dashboard(app, Path(s.web_dist))
    return app


def _mount_dashboard(app: FastAPI, dist: Path) -> None:
    """Serve the built dashboard (web/dist) on the API's port, with client-side routes falling back to index.html.
    Registered last, so every /api route wins; paths are confined to the dist directory."""
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def dashboard(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        if path:
            f = (root / path).resolve()
            if f.is_file() and root in f.parents:
                return FileResponse(f)
            if "." in path.rsplit("/", 1)[-1]:  # a missing asset is a 404, not the app shell
                raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
