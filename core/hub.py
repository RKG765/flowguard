"""WebSocket fan-out hub and one-time WebSocket tickets.

``publish`` is thread-safe (the ingest thread calls it). Each client has a bounded queue; when a slow client's queue
is full the oldest message is dropped and counted, so one slow browser cannot stall ingest or other clients.
"""
from __future__ import annotations

import asyncio
import secrets
import threading
import time
from typing import Any, Dict, Optional, Set, Tuple


class Hub:
    def __init__(self, queue_size: int = 1000) -> None:
        self.queue_size = queue_size
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Set[asyncio.Queue] = set()
        self.dropped_total = 0
        self.published_total = 0

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    @property
    def clients(self) -> int:
        return len(self._clients)

    def _fanout(self, msg: Dict[str, Any]) -> None:
        self.published_total += 1
        for q in list(self._clients):
            if q.full():
                try:
                    q.get_nowait()
                    self.dropped_total += 1
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)

    def publish(self, msg: Dict[str, Any]) -> None:
        """Safe to call from any thread. Silently a no-op before the event loop is attached."""
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, msg)
        except RuntimeError:  # loop shutting down
            pass


class TicketBook:
    """Short-lived, single-use tickets so the WebSocket handshake never carries the session token in a URL."""

    def __init__(self, ttl_seconds: float) -> None:
        self.ttl = ttl_seconds
        self._tickets: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def issue(self, user: Dict[str, Any]) -> str:
        t = secrets.token_urlsafe(24)
        now = time.time()
        with self._lock:
            self._tickets = {k: v for k, v in self._tickets.items() if v[0] > now}
            self._tickets[t] = (now + self.ttl, user)
        return t

    def redeem(self, ticket: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._tickets.pop(ticket, None)
        if item is None or item[0] < time.time():
            return None
        return item[1]
