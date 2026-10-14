"""Background thread: ZeroMQ PULL (bind) for live records + periodic ordered spool reading with acknowledgement."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import zmq

from ..config import CoreSettings
from ..ingest import Ingestor, SpoolTail

log = logging.getLogger("flowguard.core.receiver")


class Receiver(threading.Thread):
    def __init__(self, ingestor: Ingestor, settings: CoreSettings, tail: SpoolTail) -> None:
        super().__init__(name="flowguard-receiver", daemon=True)
        self.ingestor, self.s, self.tail = ingestor, settings, tail
        self._stop_evt = threading.Event()
        self.status: Dict[str, Any] = {"bound": False, "endpoint": settings.endpoint, "error": None,
                                       "last_zmq_t": None, "last_spool_poll_t": None, "zmq_records": 0}

    def stop(self) -> None:
        self._stop_evt.set()

    def _bind(self, ctx: zmq.Context) -> Optional[zmq.Socket]:
        ep = self.s.endpoint
        if ep.startswith("ipc://"):
            os.makedirs(os.path.dirname(ep[len("ipc://"):]), exist_ok=True)
        sock = ctx.socket(zmq.PULL)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVHWM, 10000)
        try:
            sock.bind(ep)
        except zmq.ZMQError as exc:  # e.g. another core already bound: keep going in spool-only mode
            self.status["error"] = f"bind {ep}: {exc}"
            log.error("receiver could not bind %s: %s (spool-only mode)", ep, exc)
            sock.close(0)
            return None
        self.status["bound"] = True
        return sock

    def run(self) -> None:
        ctx = zmq.Context.instance()
        sock = self._bind(ctx)
        next_spool = 0.0
        try:
            while not self._stop_evt.is_set():
                if sock is not None and sock.poll(200):
                    for _ in range(500):
                        try:
                            raw = sock.recv(flags=zmq.NOBLOCK)
                        except zmq.Again:
                            break
                        try:
                            rec = json.loads(raw)
                        except ValueError:
                            continue
                        if isinstance(rec, dict):
                            self.ingestor.ingest(rec, "zmq")
                            self.status["zmq_records"] += 1
                            self.status["last_zmq_t"] = time.time()
                elif sock is None:
                    self._stop_evt.wait(0.2)
                now = time.time()
                if now >= next_spool:
                    try:
                        self.tail.poll(self.ingestor.ingest)
                    except Exception:
                        log.exception("spool poll failed")
                    self.status["last_spool_poll_t"] = now
                    next_spool = now + self.s.spool_poll_seconds
        finally:
            if sock is not None:
                sock.close(0)
