#!/usr/bin/env python3
"""FlowGuard lab topology: one OVS switch with four hosts (optionally a second switch).

    h1 --\                 /-- h3            (--two-switch: h3,h4 hang off s2, s1--s2 linked)
    h2 --- s1 (dpid 1) ---+
    h4 --/                 \-- ...

Explicit dpids (s1=0000000000000001, s2=0000000000000002) so the golden store can key on them.
Importable (`build_net`) by the privileged helper; also runnable as a CLI for the Phase 0 spikes.
Needs root and the system Python (apt `mininet` package).

Datapath selection: `kernel` uses the openvswitch kernel module, `user` uses the userspace
datapath (datapath_type=netdev), `auto` picks kernel when the module is present, else user.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from typing import Dict, Optional

LAB_SWITCH_PREFIX = "s"
DPIDS = {"s1": "0000000000000001", "s2": "0000000000000002"}
HOSTS = {f"h{i}": {"ip": f"10.0.0.{i}/24", "mac": f"00:00:00:00:00:0{i}"} for i in range(1, 5)}
OF_PROTOCOLS = "OpenFlow13,OpenFlow14"


def resolve_datapath(requested: str) -> str:
    """Return 'kernel' or 'user'. `auto` checks for the openvswitch kernel module."""
    if requested in ("kernel", "user"):
        return requested
    if os.path.isdir("/sys/module/openvswitch"):
        return "kernel"
    rc = subprocess.call(["modprobe", "openvswitch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "kernel" if rc == 0 and os.path.isdir("/sys/module/openvswitch") else "user"


def build_net(datapath: str = "auto", two_switch: bool = False, controller_ip: Optional[str] = "127.0.0.1",
              controller_port: int = 6653, protocols: str = OF_PROTOCOLS, fail_mode: str = "secure",
              listen_port: Optional[int] = None):
    """Create (but do not start) the lab network. Returns (net, info dict).

    controller_ip=None builds a standalone lab (OVSBridge behaviour, no controller) for connectivity tests.
    """
    from mininet.net import Mininet
    from mininet.node import OVSBridge, OVSSwitch, RemoteController
    from mininet.link import Link

    dp = resolve_datapath(datapath)
    switch_cls = OVSSwitch if controller_ip else OVSBridge
    net = Mininet(controller=None, switch=switch_cls, link=Link, build=False, autoSetMacs=False, waitConnected=False)
    kw: Dict[str, object] = {"datapath": dp}
    if controller_ip:
        kw.update(protocols=protocols, failMode=fail_mode)
        if listen_port:  # passive OpenFlow port (ptcp) for the L1 monitor session (s2 uses listen_port + 1)
            kw["listenPort"] = listen_port
    s1 = net.addSwitch("s1", dpid=DPIDS["s1"], **kw)
    kw2 = dict(kw, listenPort=listen_port + 1) if (listen_port and controller_ip) else kw
    s2 = net.addSwitch("s2", dpid=DPIDS["s2"], **kw2) if two_switch else None
    for name, spec in HOSTS.items():
        net.addHost(name, ip=spec["ip"], mac=spec["mac"])
    for name in ("h1", "h2"):
        net.addLink(net.get(name), s1)
    for name in ("h3", "h4"):
        net.addLink(net.get(name), s2 if s2 else s1)
    if s2:
        net.addLink(s1, s2)
    if controller_ip:
        c0 = net.addController(RemoteController("c0", ip=controller_ip, port=controller_port))
        _ = c0
    info = {"datapath": dp, "switches": [s.name for s in net.switches], "dpids": {s.name: s.dpid for s in net.switches},
            "two_switch": two_switch, "controller": f"{controller_ip}:{controller_port}" if controller_ip else None}
    return net, info


def wait_controller_connected(switches: list, timeout: float = 20.0) -> bool:
    """Wait until the remote OpenFlow controller connections report is_connected=true.

    Passive listeners (ptcp:) are ignored; at least one tcp: controller record per switch is required.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = subprocess.run(["ovs-vsctl", "--timeout=3", "-f", "csv", "--no-headings", "--columns=target,is_connected",
                              "list", "controller"], capture_output=True, text=True).stdout
        rows = [r for r in (ln.replace('"', "").split(",") for ln in out.splitlines()) if r[0].startswith("tcp:")]
        if len(rows) >= len(switches) and all(r[1].strip() == "true" for r in rows):
            return True
        time.sleep(0.3)
    return False


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datapath", choices=["auto", "kernel", "user"], default="auto")
    ap.add_argument("--two-switch", action="store_true")
    ap.add_argument("--no-controller", action="store_true", help="standalone learning bridge (connectivity test)")
    ap.add_argument("--controller-port", type=int, default=6653)
    ap.add_argument("--test", choices=["pingall"], help="run a test, print JSON, exit")
    ap.add_argument("--hold", action="store_true", help="keep the lab up until SIGTERM/SIGINT")
    args = ap.parse_args(argv)

    if os.geteuid() != 0:
        print("topo_basic.py must run as root (Mininet/OVS).", file=sys.stderr)
        return 1
    from mininet.log import setLogLevel
    from mininet.clean import cleanup
    setLogLevel("warning")
    cleanup()
    net, info = build_net(args.datapath, args.two_switch, None if args.no_controller else "127.0.0.1",
                          args.controller_port)
    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(flag=True))
    try:
        net.start()
        if not args.no_controller:
            info["controller_connected"] = wait_controller_connected([s.name for s in net.switches])
        if args.test == "pingall":
            time.sleep(1)
            loss = net.pingAll(timeout="2")
            info["pingall_loss_percent"] = loss
            print(json.dumps(info))
            return 0 if loss == 0 else 3
        print(json.dumps(info), flush=True)
        if args.hold:
            while not stop["flag"]:
                time.sleep(0.5)
        return 0
    finally:
        net.stop()
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
