#!/usr/bin/env python3
"""Throw-away FlowGuard stack for the live dashboard tests: Mininet lab + engine + core, all in one data dir.

Run as root with the core venv (Mininet needs root):
    .venv-core/bin/python tests/e2e_live/stack.py --core-port 18788 --response-mode alert_only
Prints FLOWGUARD-STACK-READY when the engine reports the switch ready; stops everything on SIGTERM/SIGINT.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "topo"))
DPID = "0000000000000001"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core-port", type=int, default=18788)
    ap.add_argument("--response-mode", choices=["restore", "alert_only"], default="alert_only")
    ap.add_argument("--data", default="/tmp/fg-e2e-live")
    args = ap.parse_args()
    if os.geteuid() != 0:
        print("stack.py must run as root (Mininet/OVS)", file=sys.stderr)
        return 1

    import topo_basic
    from engine.crypto import generate_key_file

    subprocess.run(["mn", "-c"], capture_output=True)
    data = Path(args.data)
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    key = data / "keys" / "hmac.key"
    generate_key_file(str(key))
    policy = data / "policy.yaml"
    shutil.copy(REPO / "engine" / "policies" / "lab_default.yaml", policy)

    env = dict(os.environ, PYTHONPATH=str(REPO), FLOWGUARD_DATA_DIR=str(data), FLOWGUARD_KEY_FILE=str(key),
               FLOWGUARD_POLICY=str(policy), FLOWGUARD_RESPONSE_MODE=args.response_mode, FLOWGUARD_GRACE_MS="300",
               FLOWGUARD_RECONCILE_S="2", FLOWGUARD_CONFIG=str(data / "no-config.yaml"))
    env.pop("FLOWGUARD_HMAC_KEY", None)
    procs = []
    procs.append(subprocess.Popen([str(REPO / ".venv-engine/bin/ryu-manager"), "--ofp-tcp-listen-port", "6653", "engine.app"],
                                  cwd=str(REPO), env=env, stdout=open(data / "engine.log", "w"), stderr=subprocess.STDOUT))
    procs.append(subprocess.Popen([str(REPO / ".venv-core/bin/uvicorn"), "--factory", "core.main:create_app", "--host", "127.0.0.1",
                                   "--port", str(args.core_port)], cwd=str(REPO), env=env,
                                  stdout=open(data / "core.log", "w"), stderr=subprocess.STDOUT))
    time.sleep(3)
    net, _ = topo_basic.build_net("auto", False, "127.0.0.1", 6653, listen_port=topo_basic.MONITOR_PORT)
    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(flag=True))
    try:
        net.start()
        status = data / "run" / "engine_status.json"
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if json.loads(status.read_text()).get("ready", {}).get(DPID):
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
        net.pingAll(timeout="1")  # lets the learning switch see the hosts (shown on the topology page)
        print("FLOWGUARD-STACK-READY", flush=True)
        while not stop["flag"]:
            time.sleep(0.5)
        return 0
    finally:
        net.stop()
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
        subprocess.run(["mn", "-c"], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
