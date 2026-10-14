"""Non-blocking event channel from the engine to the core service (ZeroMQ PUSH, ADR-002).

``publish`` never blocks: events go into a bounded queue; a pump loop sends them with ``zmq.NOBLOCK`` (so plain
pyzmq is safe inside Ryu's eventlet loop). When the queue is full, or no core is listening and the queue backs
up, new events are dropped and counted in ``dropped_total`` (surfaced as a health metric). Alerts are made
durable separately in the spool BEFORE they reach this channel, so a dropped alert can be replayed.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional


class EventChannel:
    def __init__(self, endpoint: str, maxsize: int = 2000, zmq_module: Any = None) -> None:
        if zmq_module is None:
            import zmq as zmq_module  # type: ignore[no-redef]
        self._zmq = zmq_module
        self.endpoint = endpoint
        self.maxsize = maxsize
        self._queue: Deque[bytes] = deque()
        self.dropped_total = 0
        self.sent_total = 0
        self._ctx = zmq_module.Context.instance()
        self._sock = self._ctx.socket(zmq_module.PUSH)
        self._sock.setsockopt(zmq_module.LINGER, 0)
        self._sock.setsockopt(zmq_module.SNDHWM, 1000)
        self._sock.connect(endpoint)
        self._stop = False

    def publish(self, event: Dict[str, Any]) -> bool:
        """Queue an event. Returns False (and counts a drop) when the queue is full. Never blocks, never raises."""
        try:
            data = json.dumps(event, sort_keys=True, default=str).encode("utf-8")
        except Exception:  # publish must never raise into the Ryu event loop, whatever the event holds
            self.dropped_total += 1
            return False
        if len(self._queue) >= self.maxsize:
            self.dropped_total += 1
            return False
        self._queue.append(data)
        return True

    def pump_once(self) -> int:
        """Send as many queued events as the socket accepts right now. Returns how many were sent."""
        sent = 0
        while self._queue:
            try:
                self._sock.send(self._queue[0], flags=self._zmq.NOBLOCK)
            except self._zmq.Again:
                break  # nobody is listening / high-water mark reached: keep the event queued
            self._queue.popleft()
            sent += 1
        self.sent_total += sent
        return sent

    def run(self, sleep: Callable[[float], None], interval: float = 0.05) -> None:
        """Pump loop for a green thread / thread: ``hub.spawn(channel.run, hub.sleep)``."""
        while not self._stop:
            self.pump_once()
            sleep(interval)

    def stop(self) -> None:
        self._stop = True

    def close(self) -> None:
        self._stop = True
        self._sock.close(0)

    def health(self) -> Dict[str, int]:
        return {"queued": len(self._queue), "sent_total": self.sent_total, "dropped_total": self.dropped_total}
