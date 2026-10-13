"""Phase 0 spike controller (NOT the product engine).

Purpose: answer, with measurements, whether FlowGuard L1 can be event-driven.
  * installs the agreed table layout: table 0 = security/ACL rules (miss -> goto_table:1),
    table 1 = learning switch (miss -> controller)
  * FG_SPIKE_MODE=of14   -> OpenFlow 1.4 OFPMP_FLOW_MONITOR
    FG_SPIKE_MODE=nxst13 -> OpenFlow 1.3 + Nicira NXST_FLOW_MONITOR (hand-built experimenter message)
  * in parallel polls table 0 with a targeted OFPFlowStatsRequest(table_id=0) every FG_SPIKE_POLL seconds
  * appends every observation as one JSON line (wall clock `t`) to FG_SPIKE_LOG
Run with the engine venv: .venv-engine/bin/ryu-manager scripts/spike/ryu_spike_app.py
"""
import hashlib
import json
import os
import struct
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ethernet, packet
from ryu.ofproto import ofproto_v1_3, ofproto_v1_4

MODE = os.environ.get("FG_SPIKE_MODE", "of14")
LOG_PATH = os.environ.get("FG_SPIKE_LOG", "/tmp/fg_spike.jsonl")
POLL_INTERVAL = float(os.environ.get("FG_SPIKE_POLL", "0.5"))
NX_VENDOR = 0x2320
NXST_FLOW_MONITOR = 2
NXFMF_INITIAL, NXFMF_ADD, NXFMF_DELETE, NXFMF_MODIFY, NXFMF_ACTIONS = 1, 2, 4, 8, 16
NX_EVENTS = {0: "added", 1: "deleted", 2: "modified", 3: "abbrev", 4: "paused", 5: "resumed"}
COOKIE_ACL_DROP = 0xAAAA000000000001
COOKIE_ACL_PERMIT = 0xAAAA000000000002


class SpikeApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_4.OFP_VERSION] if MODE == "of14" else [ofproto_v1_3.OFP_VERSION]
    # FG_SPIKE_MODE: of14 | nxst13 (both rejected by OVS 2.17, kept as negative evidence) | of13 (polling only)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.poll_sent = {}
        self.dp = None
        self._log = open(LOG_PATH, "a", buffering=1)
        self.emit("app_start", mode=MODE, poll=POLL_INTERVAL)

    # ---- logging -------------------------------------------------------------------------------
    def emit(self, kind, **kw):
        kw.update(kind=kind, t=time.time())
        self._log.write(json.dumps(kw, default=str) + "\n")

    # ---- pipeline ------------------------------------------------------------------------------
    def add_flow(self, dp, table, prio, match, instructions, cookie=0):
        parser = dp.ofproto_parser
        dp.send_msg(parser.OFPFlowMod(datapath=dp, cookie=cookie, table_id=table, command=dp.ofproto.OFPFC_ADD,
                                      priority=prio, match=match, instructions=instructions))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_features(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.dp = dp
        self.emit("switch_connected", dpid=dp.id, version=ofp.OFP_VERSION)
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
                                      out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY, match=parser.OFPMatch()))
        # table 0: ACL layer
        goto1 = [parser.OFPInstructionGotoTable(1)]
        self.add_flow(dp, 0, 0, parser.OFPMatch(), goto1)
        self.add_flow(dp, 0, 100, parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=23), [], COOKIE_ACL_DROP)
        self.add_flow(dp, 0, 90, parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=22), goto1, COOKIE_ACL_PERMIT)
        # table 1: learning switch, miss -> controller
        to_ctrl = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                                [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])]
        self.add_flow(dp, 1, 0, parser.OFPMatch(), to_ctrl)
        hub.spawn(self._start_observers, dp)

    def _start_observers(self, dp):
        hub.sleep(1.0)  # let the pipeline land before the initial monitor snapshot
        if MODE == "of14":
            self._start_of14_monitor(dp)
        elif MODE == "nxst13":
            self._start_nxst_monitor(dp)
        # MODE == "of13": no in-band monitor; an external OpenFlow 1.0 NXST monitor session is used
        hub.spawn(self._poll_loop, dp)

    # ---- learning switch (table 1) -------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        table = self.mac_to_port.setdefault(dp.id, {})
        table[eth.src] = in_port
        out_port = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofp.OFPP_FLOOD:
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
            self.add_flow(dp, 1, 10, parser.OFPMatch(eth_dst=eth.dst), inst)
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
                                        actions=actions, data=msg.data))

    # ---- OpenFlow 1.4 flow monitor -------------------------------------------------------------
    def _start_of14_monitor(self, dp):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        flags = (ofp.OFPFMF_INITIAL | ofp.OFPFMF_ADD | ofp.OFPFMF_REMOVED | ofp.OFPFMF_MODIFY |
                 ofp.OFPFMF_INSTRUCTIONS | ofp.OFPFMF_NO_ABBREV)
        req = parser.OFPFlowMonitorRequest(dp, 0, 1, ofp.OFPP_ANY, ofp.OFPG_ANY, flags, 0, ofp.OFPFMC_ADD)
        self.emit("monitor_request", mode="of14", table_id=0)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowMonitorReply, MAIN_DISPATCHER)
    def on_of14_monitor(self, ev):
        now = time.time()
        for upd in ev.msg.body:
            event = getattr(upd, "event", None)
            self.emit("monitor", mode="of14", t_rx=now, event=event, table_id=getattr(upd, "table_id", None),
                      priority=getattr(upd, "priority", None), cookie=getattr(upd, "cookie", None),
                      cls=type(upd).__name__)

    # ---- Nicira NXST flow monitor (OpenFlow 1.3) -----------------------------------------------
    def _start_nxst_monitor(self, dp):
        parser = dp.ofproto_parser
        flags = NXFMF_INITIAL | NXFMF_ADD | NXFMF_DELETE | NXFMF_MODIFY | NXFMF_ACTIONS
        # struct nx_flow_monitor_request: id(4) flags(2) out_port(2) match_len(2) table_id(1) zeros(5); empty match
        body = struct.pack("!IHHHB5x", 7, flags, 0xFFFF, 0, 0xFF)
        self.emit("monitor_request", mode="nxst13", bytes=len(body))
        dp.send_msg(parser.OFPExperimenterStatsRequest(dp, 0, NX_VENDOR, NXST_FLOW_MONITOR, body))

    @set_ev_cls(ofp_event.EventOFPExperimenterStatsReply, MAIN_DISPATCHER)
    def on_nxst_monitor(self, ev):
        now = time.time()
        data = ev.msg.body.data if hasattr(ev.msg.body, "data") else b""
        if getattr(ev.msg.body, "exp_type", None) != NXST_FLOW_MONITOR:
            self.emit("nxst_other", exp_type=getattr(ev.msg.body, "exp_type", None))
            return
        off = 0
        while off + 4 <= len(data):
            length, event = struct.unpack_from("!HH", data, off)
            if length < 4:
                break
            if event in (0, 1, 2):  # nx_flow_update_full
                _, _, reason, prio, idle, hard, mlen, table_id, cookie = struct.unpack_from("!HHHHHHHBxQ", data, off)
                self.emit("monitor", mode="nxst13", t_rx=now, event=NX_EVENTS[event], table_id=table_id,
                          priority=prio, cookie=cookie, cls="nx_flow_update_full")
            else:
                self.emit("monitor", mode="nxst13", t_rx=now, event=NX_EVENTS.get(event, event), table_id=None,
                          priority=None, cookie=None, cls="nx_flow_update_other")
            off += length

    # ---- targeted polling of table 0 -----------------------------------------------------------
    def _poll_loop(self, dp):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        while True:
            req = parser.OFPFlowStatsRequest(dp, 0, 0, ofp.OFPP_ANY, ofp.OFPG_ANY, 0, 0, parser.OFPMatch())
            dp.send_msg(req)
            self.poll_sent[req.xid] = time.time()
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def on_flow_stats(self, ev):
        now = time.time()
        sent = self.poll_sent.pop(ev.msg.xid, None)
        rows = []
        for st in ev.msg.body:
            rows.append([st.table_id, st.priority, json.dumps(st.match.to_jsondict(), sort_keys=True),
                         json.dumps([i.to_jsondict() for i in st.instructions], sort_keys=True), st.cookie])
        rows.sort()
        digest = hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]
        self.emit("poll", t_send=sent, t_recv=now, rtt_ms=(now - sent) * 1000 if sent else None, n=len(rows),
                  tables=sorted({r[0] for r in rows}), digest=digest)
