"""FlowGuard L1 engine: a Ryu (OpenFlow 1.3) application.

Run:  PYTHONPATH=<repo> .venv-engine/bin/ryu-manager engine.app

What it does
  * installs the policy as SIGNED rules (HMAC in the cookie) through ``install_signed_rule`` and records them in
    the golden store
  * watches each switch through an OpenFlow 1.0 Nicira flow-monitor session on a passive port (ADR-004); every
    live change in a critical table triggers a targeted OFPFlowStatsRequest(table_id) which is compared with the
    golden store (``verifier.classify``)
  * restores altered/missing rules and removes forged/shadow rules (``responder``), rate limited, then confirms
  * raises ``unattributed_change`` when a critical-table change the engine did not cause leaves no trace in the
    rules (a tamper-and-revert)
  * writes every alert to the durable spool first, then to the non-blocking ZeroMQ channel
Table layout (ADR-006): table 0 = signed security/ACL rules, table 1 = unsigned learning switch.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import shutil
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from eventlet.green import subprocess as gsub
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ethernet, packet
from ryu.ofproto import ofproto_v1_3

from engine import ryu_codec
from engine.canonical import CanonicalError, RuleSpec, dpid_hex
from engine.channel import EventChannel
from engine.config import EngineConfig, load_config
from engine.crypto import EpochPolicy, KeyMaterialError, Signer, load_master_key
from engine.monitor_parser import MonitorEvent, MonitorParser
from engine.policy import PolicyError, PolicyRule, diff, file_signature, load_policy, rules_for
from engine.responder import DELETE, NONE, RESTORE, PlannedAction, Responder
from engine.spool import AlertSpool
from engine.store import GoldenStore
from engine.verifier import (ALTERED, FORGED, MISSING, SHADOW, Deduper, Finding, ObservedRule, Pending, classify,
                             explain)

SEVERITY = {MISSING: "high", ALTERED: "high", SHADOW: "high", FORGED: "high", "unattributed_change": "medium",
            "monitor_down": "medium", "restore_rate_limited": "high", "spool_overflow": "high", "policy_invalid": "low",
            "verify_timeout": "medium", "unparseable_rule": "medium", "store_error": "high"}
SlotKey = Tuple[str, int, int, str]  # dpid, table, priority, match_key


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"t": round(record.created, 3), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        extra = getattr(record, "fields", None)
        if extra:
            base.update(extra)
        return json.dumps(base, default=str, sort_keys=True)


def _setup_logging() -> logging.Logger:
    log = logging.getLogger("flowguard")
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_JsonFormatter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


class _Pass:
    """One verification pass: a targeted stats request for one critical table of one switch."""

    def __init__(self, dp: Any, table_id: int, reason: str, triggers: List[MonitorEvent]) -> None:
        self.dp, self.table_id, self.reason, self.triggers = dp, table_id, reason, triggers
        self.rows: List[Any] = []
        self.t_request = 0.0
        self.xid = -1


class _Incident:
    def __init__(self, alert_id: str, kind: str, t_detect: float, t_event: Optional[float]) -> None:
        self.alert_id, self.kind, self.t_detect, self.t_event = alert_id, kind, t_detect, t_event
        self.t_response_sent: Optional[float] = None
        self.t_applied: Optional[float] = None


class FlowGuardEngine(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.log = _setup_logging()
        self.cfg: EngineConfig = load_config()
        os.makedirs(self.cfg.run_dir, mode=0o700, exist_ok=True)
        os.makedirs(os.path.dirname(self.cfg.db_path), mode=0o700, exist_ok=True)
        try:
            key = load_master_key(self.cfg.key_file)
        except KeyMaterialError as exc:
            self.log.error("refusing to start: %s", exc)
            raise SystemExit(f"flowguard engine: {exc}")
        self.store = GoldenStore(self.cfg.db_path)
        epoch = self.store.load_epoch_policy(self.cfg.rotation_grace_seconds) or EpochPolicy(grace_seconds=self.cfg.rotation_grace_seconds)
        self.signer = Signer(key, epoch)
        self.store.save_epoch_policy(epoch)
        self.pending = Pending(self.cfg.grace_window_ms / 1000.0)
        self.deduper = Deduper(self.cfg.alert_dedupe_seconds)
        self.responder = Responder(self.cfg.response_mode, self.cfg.restore_rate_limit_per_minute)
        self.spool = AlertSpool(self.cfg.spool_path, self.cfg.spool_max_bytes, self.cfg.spool_backups)
        self.channel = EventChannel(self.cfg.event_endpoint, self.cfg.event_queue_max)
        self.eventlog = open(self.cfg.eventlog_path, "a", buffering=1)
        self.critical = set(self.cfg.critical_tables)
        try:
            self.policy: List[PolicyRule] = load_policy(self.cfg.policy_path)
        except PolicyError as exc:
            self.log.error("refusing to start: %s", exc)
            raise SystemExit(f"flowguard engine: {exc}")
        self._policy_sig = file_signature(self.cfg.policy_path)

        self.dps: Dict[str, Any] = {}
        self.monitors_up: Dict[str, bool] = {}
        self.synced: Dict[str, bool] = {}
        self._monitor_running: Dict[str, bool] = {}
        self._xid_pass: Dict[int, _Pass] = {}            # passes in flight, by request xid
        self._scheduled: Dict[Tuple[str, int], Tuple[float, int]] = {}  # (dpid, table) -> (run_at, generation)
        self._pass_gen = itertools.count(1)
        self.unexplained: Dict[Tuple[str, int], List[MonitorEvent]] = {}
        self.incidents: Dict[SlotKey, _Incident] = {}
        self.mac_to_port: Dict[str, Dict[str, int]] = {}
        self.counters = {"alerts": 0, "passes": 0, "events": 0, "events_attributed": 0, "restores": 0, "deletes": 0}
        self.started = time.time()

        hub.spawn(self.channel.run, hub.sleep)
        hub.spawn(self._policy_watcher)
        hub.spawn(self._reconcile_loop)
        hub.spawn(self._status_loop)
        self.emit("engine_start", key_fingerprint=self.signer.fingerprint(), epoch=self.signer.policy.current,
                  critical_tables=sorted(self.critical), response_mode=self.cfg.response_mode,
                  golden_rules=self.store.count(), mode=self.cfg.verify_mode)

    # ---- output ----------------------------------------------------------------------------------------------
    def emit(self, kind: str, **fields: Any) -> Dict[str, Any]:
        """Best-effort event: event log + structured log + channel (never raises, never blocks)."""
        ev = dict(fields, kind=kind, t=time.time())
        try:
            self.eventlog.write(json.dumps(ev, sort_keys=True, default=str) + "\n")
        except (OSError, ValueError):
            pass
        self.log.info(kind, extra={"fields": fields})
        self.channel.publish(dict(ev, type="event"))
        return ev

    def raise_alert(self, kind: str, **fields: Any) -> Dict[str, Any]:
        """Durable alert: spool first (fsync), then channel and event log."""
        self.counters["alerts"] += 1
        alert = dict(fields, id=uuid.uuid4().hex, kind=kind, layer="L1", severity=SEVERITY.get(kind, "medium"), t=time.time())
        try:
            res = self.spool.append(dict(alert, type="alert"))
            alert["seq"] = res.seq
            if res.overflowed:
                self.spool.append({"type": "alert", "kind": "spool_overflow", "layer": "L1", "severity": "high",
                                   "t": time.time(), "id": uuid.uuid4().hex, "dropped": res.dropped,
                                   "summary": f"The alert spool is full; {res.dropped} unacknowledged alerts were discarded."})
        except OSError as exc:
            self.log.error("spool write failed: %s", exc)
            alert["spool_error"] = str(exc)
        self.channel.publish(dict(alert, type="alert"))
        self.emit("alert", alert_id=alert["id"], alert_kind=kind, **{k: v for k, v in fields.items() if k in ("dpid", "table_id", "priority", "action")})
        return alert

    # ---- switch lifecycle --------------------------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_features(self, ev: Any) -> None:
        dp = ev.msg.datapath
        dpid = dpid_hex(dp.id)
        self.dps[dpid] = dp
        self.synced[dpid] = False
        self.emit("switch_connected", dpid=dpid)
        if self.cfg.learning_switch:
            self._install_learning_miss(dp)
        self._apply_connect_policy(dp)
        if self.cfg.verify_mode == "event" and not self._monitor_running.get(dpid):
            self._monitor_running[dpid] = True
            hub.spawn(self._monitor_loop, dpid, self.cfg.monitor_port(dp.id))
        self.schedule_pass(dpid, None, "startup", delay=self.pending.grace + 0.1)
        self.synced[dpid] = True

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def on_state(self, ev: Any) -> None:
        if ev.state == DEAD_DISPATCHER and ev.datapath is not None:
            dpid = dpid_hex(ev.datapath.id)
            if self.dps.get(dpid) is ev.datapath:
                self.dps.pop(dpid, None)
                self.synced[dpid] = False
                self.monitors_up[dpid] = False
                self.emit("switch_disconnected", dpid=dpid)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def on_error(self, ev: Any) -> None:
        msg = ev.msg
        self.log.warning("openflow_error", extra={"fields": {"dpid": dpid_hex(msg.datapath.id), "type": msg.type, "code": msg.code}})

    # ---- signed installs -----------------------------------------------------------------------------------------
    def install_signed_rule(self, dp: Any, spec: RuleSpec) -> int:
        """The ONLY way the controller installs a protected rule: sign, record as golden, then send."""
        dpid = dpid_hex(dp.id)
        epoch = self.signer.policy.current
        cookie = self.signer.cookie_for(dpid, spec, epoch)
        self.store.put(dpid, spec, epoch, cookie)
        self.pending.expect(dpid, spec.table_id, cookie, ("added", "modified"), slot=spec.key())
        dp.send_msg(ryu_codec.flow_add(dp, spec, cookie))
        return cookie

    def retire_rule(self, dp: Any, spec: RuleSpec) -> None:
        dpid = dpid_hex(dp.id)
        g = self.store.get(dpid, spec)
        self.store.delete(dpid, spec)
        if g is not None:
            self.pending.expect(dpid, spec.table_id, g.cookie, ("deleted",), slot=spec.key())
        dp.send_msg(ryu_codec.flow_delete_strict(dp, spec))

    def _desired(self, dpid: str) -> List[RuleSpec]:
        return [s for s in rules_for(self.policy, dpid) if s.table_id in self.critical]

    def _apply_connect_policy(self, dp: Any) -> None:
        dpid = dpid_hex(dp.id)
        desired = self._desired(dpid)
        keep = {s.key() for s in desired}
        for g in self.store.list(dpid):
            if g.spec.table_id in self.critical and g.spec.key() not in keep:
                self.retire_rule(dp, g.spec)  # policy changed while the engine was down: signed retirement, no alert
        for spec in desired:
            self.install_signed_rule(dp, spec)
        self.emit("policy_applied", dpid=dpid, installed=len(desired), reason="connect")

    def _apply_policy_change(self, old: List[PolicyRule], new: List[PolicyRule]) -> None:
        for dpid, dp in list(self.dps.items()):
            install, retire = diff(rules_for(old, dpid), rules_for(new, dpid))
            for spec in retire:
                if spec.table_id in self.critical:
                    self.retire_rule(dp, spec)
            for spec in install:
                if spec.table_id in self.critical:
                    self.install_signed_rule(dp, spec)
            self.emit("policy_applied", dpid=dpid, installed=len(install), retired=len(retire), reason="policy_file_changed")

    def rotate_key(self) -> None:
        """New key epoch: re-sign every golden rule and replace it on its switch (OFPFC_ADD is atomic)."""
        epoch = self.signer.policy.rotate(time.time())
        self.store.save_epoch_policy(self.signer.policy)
        for dpid, dp in list(self.dps.items()):
            for g in self.store.list(dpid):
                if g.spec.table_id in self.critical:
                    self.install_signed_rule(dp, g.spec)
        self.emit("key_rotated", epoch=epoch, previous_epoch=self.signer.policy.previous,
                  grace_seconds=self.signer.policy.grace_seconds)

    # ---- learning switch (table 1, unsigned, not verified) ---------------------------------------------------
    def _install_learning_miss(self, dp: Any) -> None:
        ofp, parser = dp.ofproto, dp.ofproto_parser
        to_ctrl = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=1, command=ofp.OFPFC_ADD, priority=0,
                                      match=parser.OFPMatch(), instructions=to_ctrl))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev: Any) -> None:
        if not self.cfg.learning_switch:
            return
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        table = self.mac_to_port.setdefault(dpid_hex(dp.id), {})
        table[eth.src] = in_port
        out = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out)]
        if out != ofp.OFPP_FLOOD:
            dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=1, command=ofp.OFPFC_ADD, priority=10,
                                          match=parser.OFPMatch(eth_dst=eth.dst),
                                          instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]))
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port, actions=actions, data=msg.data))

    # ---- monitor session (OpenFlow 1.0 NXST via ovs-ofctl) -----------------------------------------------------
    def _monitor_loop(self, dpid: str, port: int) -> None:
        exe = shutil.which("ovs-ofctl")
        stdbuf = shutil.which("stdbuf")
        backoff = 1.0
        was_down = False
        while dpid in self.dps:
            if not exe:
                self.raise_alert("monitor_down", dpid=dpid, summary="ovs-ofctl is not installed; change detection falls back to the slow poll.")
                return
            cmd = ([stdbuf, "-oL", "-eL"] if stdbuf else []) + [exe, "monitor", f"tcp:127.0.0.1:{port}", "watch:!initial"]
            try:
                proc = gsub.Popen(cmd, stdout=gsub.PIPE, stderr=gsub.STDOUT)
            except OSError as exc:
                self.log.error("monitor spawn failed: %s", exc)
                hub.sleep(backoff)
                continue
            hub.sleep(0.4)
            if proc.poll() is None:
                self.monitors_up[dpid] = True
                backoff = 1.0
                self.emit("monitor_up", dpid=dpid, port=port)
                if was_down:
                    self.emit("monitor_recovered", dpid=dpid)
                    was_down = False
                self.schedule_pass(dpid, None, "monitor_up", delay=0.0)  # cover anything missed before the session existed
                parser = MonitorParser()
                try:
                    while True:
                        raw = proc.stdout.readline()
                        if not raw:
                            break
                        ev = parser.feed(raw.decode("utf-8", "replace"))
                        if ev is not None:
                            self.on_monitor_event(dpid, ev)
                except Exception:  # a parser/handler bug must not kill the supervisor
                    self.log.exception("monitor reader failed")
            self.monitors_up[dpid] = False
            try:
                proc.kill()
            except OSError:
                pass
            if dpid not in self.dps:
                break
            if not was_down:
                was_down = True
                self.raise_alert("monitor_down", dpid=dpid, summary="The change-monitor session to the switch dropped. Detection is limited to the slow poll until it reconnects.")
            hub.sleep(backoff)
            backoff = min(backoff * 2, 10.0)
        self._monitor_running[dpid] = False

    def on_monitor_event(self, dpid: str, ev: MonitorEvent) -> None:
        if ev.initial:
            return
        self.counters["events"] += 1
        if ev.event in ("paused", "resumed"):
            self.emit("monitor_" + ev.event, dpid=dpid)
            self.schedule_pass(dpid, None, "monitor_resync", delay=0.0)
            return
        if ev.table_id is None or ev.table_id not in self.critical:
            return
        hit = self.pending.match(dpid, ev.table_id, ev.event, ev.cookie if ev.cookie is not None else -1, ev.t_rx)
        if hit is not None:
            self.counters["events_attributed"] += 1
            inc = self.incidents.get(hit.tag) if hit.tag else None  # type: ignore[arg-type]
            if inc is not None and inc.t_applied is None:
                inc.t_applied = ev.t_rx
            # attribution is by cookie and can be spoofed inside the grace window, so also look at the real table
            self.schedule_pass(dpid, ev.table_id, "attributed_check", delay=self.pending.grace + 0.05)
            return
        self.unexplained.setdefault((dpid, ev.table_id), []).append(ev)
        self.schedule_pass(dpid, ev.table_id, "monitor_event", delay=self.cfg.verify_debounce_ms / 1000.0)

    # ---- verification passes ------------------------------------------------------------------------------------
    def schedule_pass(self, dpid: str, table_id: Optional[int], reason: str, delay: float = 0.0) -> None:
        """Queue a verification pass. A pass that would run EARLIER than one already queued supersedes it, so a
        live monitor event is never held back by a slower pass (e.g. a delayed confirmation pass)."""
        tables = [table_id] if table_id is not None else sorted(self.critical)
        for t in tables:
            key = (dpid, t)
            run_at = time.time() + delay
            cur = self._scheduled.get(key)
            if cur is not None and cur[0] <= run_at:
                continue  # an equal-or-earlier pass is already waiting
            gen = next(self._pass_gen)
            self._scheduled[key] = (run_at, gen)
            hub.spawn(self._run_pass_later, dpid, t, reason, delay, gen)

    def _run_pass_later(self, dpid: str, table_id: int, reason: str, delay: float, gen: int) -> None:
        try:
            if delay > 0:
                hub.sleep(delay)
            cur = self._scheduled.get((dpid, table_id))
            if cur is None or cur[1] != gen:
                return  # superseded by an earlier pass; that pass does the work
            del self._scheduled[(dpid, table_id)]
            dp = self.dps.get(dpid)
            if dp is None:
                return
            triggers = self.unexplained.pop((dpid, table_id), [])
            ps = _Pass(dp, table_id, reason, triggers)
            req = ryu_codec.flow_stats_request(dp, table_id)
            ps.t_request = time.time()
            dp.send_msg(req)
            ps.xid = req.xid
            self._xid_pass[req.xid] = ps
            hub.spawn(self._pass_timeout, ps)
        except Exception:
            self.log.exception("could not start verification pass")

    def _pass_timeout(self, ps: _Pass) -> None:
        hub.sleep(self.cfg.stats_timeout_seconds)
        if self._xid_pass.pop(ps.xid, None) is not None:
            dpid = dpid_hex(ps.dp.id)
            self.unexplained.setdefault((dpid, ps.table_id), []).extend(ps.triggers)  # keep the triggers for the retry
            self.raise_alert("verify_timeout", dpid=dpid, table_id=ps.table_id, summary="The switch did not answer a rule-table request in time; verification will be retried.")
            self.schedule_pass(dpid, ps.table_id, "retry", delay=0.5)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def on_flow_stats(self, ev: Any) -> None:
        msg = ev.msg
        ps = self._xid_pass.get(msg.xid)
        if ps is None:
            return
        ps.rows.extend(msg.body)
        if msg.flags & msg.datapath.ofproto.OFPMPF_REPLY_MORE:
            return
        self._xid_pass.pop(msg.xid, None)
        try:
            self._finish_pass(ps)
        except Exception:
            self.log.exception("verification pass failed")

    def _finish_pass(self, ps: _Pass) -> None:
        t_reply = time.time()
        self.counters["passes"] += 1
        dp, dpid, table = ps.dp, dpid_hex(ps.dp.id), ps.table_id
        observed: List[ObservedRule] = []
        for stat in ps.rows:
            try:
                observed.append(ryu_codec.stat_to_observed(stat))
            except CanonicalError as exc:
                # cannot verify -> alert only, NEVER act on a rule we could not interpret
                self.raise_alert("unparseable_rule", dpid=dpid, table_id=table, priority=getattr(stat, "priority", None),
                                 cookie=f"{int(stat.cookie):016x}", action="none", summary=f"A rule in the protected table could not be interpreted ({exc}); no automatic action was taken.")
        golden = self.store.list(dpid, table)
        findings = classify(dpid, observed, golden, self.signer, t_reply, self.pending.live_slots(dpid, t_reply))
        t_classified = time.time()
        event_ts = [e.t_rx for e in ps.triggers]
        t_event = min(event_ts) if event_ts else None
        detected_by = {"reconcile": "reconcile_poll"}.get(ps.reason, ps.reason)

        bad_slots = {(f.dpid, f.spec.table_id, f.spec.priority, f.spec.match_key()) for f in findings}
        if findings:
            plans = self.responder.plan(findings, t_classified)
            for plan in plans:
                self._handle_finding(dp, plan, ps, t_event, t_reply, t_classified, detected_by)
            self.schedule_pass(dpid, table, "confirm", delay=self.pending.grace + 0.1)
        elif ps.triggers:
            # changes happened, but the table already equals the golden rules: a tamper-and-revert
            if self.deduper.should_alert((dpid, "unattributed_change", table), t_classified):
                self.raise_alert(
                    "unattributed_change", dpid=dpid, table_id=table, action="none", detected_by=detected_by,
                    events=[{"event": e.event, "cookie": None if e.cookie is None else f"{e.cookie:016x}", "match": e.match_text, "t": e.t_rx} for e in ps.triggers[:20]],
                    timing={"t_event_rx": t_event, "t_stats_request": ps.t_request, "t_stats_reply": t_reply, "t_classified": t_classified,
                            "detect_latency_ms": round((t_classified - t_event) * 1000, 2) if t_event else None},
                    summary="The protected rule table was changed by something other than the controller, and then changed back before it could be inspected. The rules look correct now, but someone with access to the switch is modifying them.")
        # close incidents whose slot is clean again
        now = time.time()
        for slot, inc in list(self.incidents.items()):
            settled = inc.t_applied is not None or (inc.t_response_sent is not None and now - inc.t_response_sent > self.pending.grace)
            if slot[0] == dpid and slot[1] == table and slot not in bad_slots and settled:
                self.incidents.pop(slot)
                t_done = inc.t_applied or now
                upd = {"type": "alert_update", "alert_id": inc.alert_id, "kind": "restored", "t": now,
                       "timing": {"t_classified": inc.t_detect, "t_response_sent": inc.t_response_sent, "t_applied": inc.t_applied, "t_confirmed": now,
                                  "time_to_restore_ms": round((t_done - inc.t_detect) * 1000, 2)}}
                try:
                    self.spool.append(upd)
                except OSError:
                    pass
                self.channel.publish(upd)
                self.emit("rule_restored", alert_id=inc.alert_id, time_to_restore_ms=upd["timing"]["time_to_restore_ms"])

    def _handle_finding(self, dp: Any, plan: PlannedAction, ps: _Pass, t_event: Optional[float], t_reply: float, t_classified: float, detected_by: str) -> None:
        f = plan.finding
        slot: SlotKey = (f.dpid, f.spec.table_id, f.spec.priority, f.spec.match_key())
        t_sent: Optional[float] = None
        if plan.op == RESTORE and f.golden is not None:
            self.pending.expect(f.dpid, f.spec.table_id, f.golden.cookie, ("added", "modified"), tag=slot, slot=f.spec.key())
            dp.send_msg(ryu_codec.flow_add(dp, f.golden.spec, f.golden.cookie))
            t_sent = time.time()
            self.counters["restores"] += 1
        elif plan.op == DELETE and f.observed is not None:
            self.pending.expect(f.dpid, f.spec.table_id, f.observed.cookie, ("deleted",), tag=slot, slot=f.spec.key())
            dp.send_msg(ryu_codec.flow_delete_strict(dp, f.observed.spec))
            t_sent = time.time()
            self.counters["deletes"] += 1
        if plan.op == NONE and plan.reason == "rate_limited":
            if self.deduper.should_alert((f.dpid, "restore_rate_limited", f.spec.table_id), t_classified):
                self.raise_alert("restore_rate_limited", dpid=f.dpid, table_id=f.spec.table_id, action="none",
                                 summary="Too many automatic repairs on this switch in the last minute; repairs are paused so the engine does not fight an attacker in a loop. Investigate the switch.")
        open_inc = self.incidents.get(slot)
        if open_inc is not None and t_classified - open_inc.t_detect < self.cfg.alert_dedupe_seconds:
            if t_sent is not None:  # same incident still being repaired: no second alert, but remember the newest response
                open_inc.t_response_sent = t_sent
            return
        if plan.op == NONE and not self.deduper.should_alert(f.key(), t_classified):
            return  # nothing is being done about it (alert-only / rate limited): do not repeat every pass
        timing = {"t_event_rx": t_event, "t_stats_request": ps.t_request, "t_stats_reply": t_reply, "t_classified": t_classified,
                  "t_response_sent": t_sent,
                  "detect_latency_ms": round((t_classified - t_event) * 1000, 2) if t_event else None,
                  "respond_latency_ms": round((t_sent - t_classified) * 1000, 2) if t_sent else None}
        alert = self.raise_alert(
            f.kind, dpid=f.dpid, table_id=f.spec.table_id, priority=f.spec.priority, match=f.spec.match,
            action={RESTORE: "restored", DELETE: "removed", NONE: "none"}[plan.op], action_reason=plan.reason,
            detected_by=detected_by, signature_valid=f.signature_valid, reasons=list(f.reasons), shadows=list(f.shadows),
            observed=None if f.observed is None else {"cookie": f"{f.observed.cookie:016x}", "instructions": list(f.observed.spec.instructions)},
            golden=None if f.golden is None else {"cookie": f"{f.golden.cookie:016x}", "instructions": list(f.golden.spec.instructions)},
            timing=timing, summary=explain(f))
        if plan.op != NONE:
            inc = _Incident(alert["id"], f.kind, t_classified, t_event)
            inc.t_response_sent = t_sent
            self.incidents[slot] = inc

    # ---- periodic work ---------------------------------------------------------------------------------------------
    def _reconcile_loop(self) -> None:
        """Safety net: even with a healthy monitor, re-verify every critical table every few seconds."""
        while True:
            hub.sleep(self.cfg.reconcile_poll_seconds)
            for dpid in list(self.dps):
                self.schedule_pass(dpid, None, "reconcile", delay=0.0)

    def _policy_watcher(self) -> None:
        control = os.path.join(self.cfg.run_dir, "control")
        os.makedirs(control, exist_ok=True)
        while True:
            hub.sleep(self.cfg.policy_poll_seconds)
            try:
                sig = file_signature(self.cfg.policy_path)
                if sig != self._policy_sig:
                    self._policy_sig = sig
                    try:
                        new = load_policy(self.cfg.policy_path)
                    except PolicyError as exc:
                        self.raise_alert("policy_invalid", action="none", summary=f"The policy file was changed but is invalid ({exc}); the previous policy stays in force.")
                    else:
                        old, self.policy = self.policy, new
                        self._apply_policy_change(old, new)
                rot = os.path.join(control, "rotate")
                if os.path.exists(rot):
                    os.remove(rot)
                    self.rotate_key()
            except Exception:
                self.log.exception("policy watcher failed")

    def _status_loop(self) -> None:
        path = os.path.join(self.cfg.run_dir, "engine_status.json")
        while True:
            try:
                status = {
                    "pid": os.getpid(), "t": time.time(), "started": self.started, "key_fingerprint": self.signer.fingerprint(),
                    "epoch": self.signer.policy.current, "switches": sorted(self.dps), "monitors_up": {k: v for k, v in self.monitors_up.items()},
                    "ready": {k: bool(self.synced.get(k) and (self.monitors_up.get(k) or self.cfg.verify_mode != "event")) for k in self.dps},
                    "golden_rules": self.store.count(), "counters": self.counters, "channel": self.channel.health(),
                    "spool": {"dropped_total": self.spool.dropped_total, "acked": self.spool.acked(), "bytes": self.spool.total_bytes()},
                    "response_mode": self.cfg.response_mode,
                }
                tmp = path + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump(status, fh)
                os.replace(tmp, path)
            except Exception:
                self.log.exception("status write failed")
            hub.sleep(1.0)
