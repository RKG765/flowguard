"""Parser for the text printed by ``ovs-ofctl monitor <switch> watch:!initial`` (OpenFlow 1.0 + Nicira NXST).

Example output (spike evidence: docs/spike_evidence/s4_ovs_monitor_cli.txt)::

    NXST_FLOW_MONITOR reply (xid=0x0):
     event=MODIFIED table=0 cookie=0x1234 ip
     event=DELETED reason=delete table=0 cookie=0 ip,nw_dst=10.0.0.3

The text carries table, cookie and a match string but NOT priority or instructions; the verifier therefore
treats an event only as a trigger and reads the table with a targeted stats request.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

_HEADER = re.compile(r"NXST_FLOW_MONITOR reply \(xid=(0x[0-9a-fA-F]+)\)")
_EVENT = re.compile(r"^\s*event=(?P<event>[A-Z]+)(?P<rest>.*)$")
_TABLE = re.compile(r"\btable=(\d+)")
_COOKIE = re.compile(r"\bcookie=(0x[0-9a-fA-F]+|\d+)")
_REASON = re.compile(r"\breason=(\w+)")


@dataclass(frozen=True)
class MonitorEvent:
    event: str  # added | deleted | modified | abbrev | paused | resumed
    table_id: Optional[int]
    cookie: Optional[int]
    match_text: str
    reason: Optional[str]
    initial: bool  # part of the reply to our own monitor request (the initial dump), not a live change
    t_rx: float
    raw: str


class MonitorParser:
    """Stateful line parser: remembers whether the current reply block is the initial dump."""

    def __init__(self) -> None:
        self._initial = False

    def feed(self, line: str, now: Optional[float] = None) -> Optional[MonitorEvent]:
        """Return a MonitorEvent for an event line, else None (headers update state; other lines are ignored)."""
        m = _HEADER.search(line)
        if m:
            self._initial = int(m.group(1), 16) != 0  # async updates use xid 0; the initial dump echoes our request xid
            return None
        e = _EVENT.match(line)
        if not e:
            return None
        rest = e.group("rest")
        t, c, r = _TABLE.search(rest), _COOKIE.search(rest), _REASON.search(rest)
        body = rest
        for rx in (_REASON, _TABLE, _COOKIE):
            body = rx.sub("", body, count=1)
        return MonitorEvent(
            event=e.group("event").lower(),
            table_id=int(t.group(1)) if t else None,
            cookie=int(c.group(1), 0) if c else None,
            match_text=" ".join(body.split()),
            reason=r.group(1) if r else None,
            initial=self._initial,
            t_rx=time.time() if now is None else now,
            raw=line.rstrip("\n"),
        )
