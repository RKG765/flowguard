#!/usr/bin/env python3
"""FlowGuard environment doctor.

Checks everything FlowGuard needs on Ubuntu 22.04 (native or WSL2) and prints a PASS/WARN/FAIL
table with a fix for every problem. Standard library only, so it runs before any venv exists.

Usage: doctor.py [--json] [--quick] [--no-color]
  --json     machine-readable output (used later by the dashboard Settings page)
  --quick    skip the Mininet ping test (slow, needs root)
Exit code: 0 when there is no FAIL, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
REQUIRED_PORTS = {6653: "OpenFlow controller (Ryu)", 8787: "FlowGuard dashboard/API"}
MIN_DISK_GB_FAIL = 2.0
MIN_DISK_GB_WARN = 5.0

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
Result = Dict[str, str]


def run(cmd: List[str], timeout: float = 20.0) -> Tuple[int, str]:
    """Run a command, returning (returncode, combined output). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(cmd)}: timed out after {timeout:.0f}s"


def res(cid: str, title: str, status: str, detail: str = "", fix: str = "") -> Result:
    return {"id": cid, "title": title, "status": status, "detail": detail, "fix": fix}


def detect_env() -> str:
    """Return 'wsl' or 'ubuntu'."""
    try:
        text = Path("/proc/version").read_text().lower()
    except OSError:
        return "ubuntu"
    return "wsl" if ("microsoft" in text or "wsl" in text) else "ubuntu"


def check_environment() -> Result:
    env = detect_env()
    kernel = os.uname().release
    return res("env", "Environment", PASS, f"env={env}, kernel={kernel}")


def check_os() -> Result:
    info: Dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v.strip('"')
    except OSError:
        return res("os", "Operating system", FAIL, "/etc/os-release unreadable",
                   "Run FlowGuard on Ubuntu 22.04.")
    name = f"{info.get('ID', '?')} {info.get('VERSION_ID', '?')}"
    if info.get("ID") != "ubuntu":
        return res("os", "Operating system", FAIL, name, "Ubuntu 22.04 is required.")
    if info.get("VERSION_ID") != "22.04":
        return res("os", "Operating system", WARN, name, "Only Ubuntu 22.04 is tested.")
    return res("os", "Operating system", PASS, name)


def check_systemd() -> Result:
    if Path("/run/systemd/system").is_dir():
        return res("systemd", "systemd", PASS, "available (units can be used)")
    fix = ("Optional: add '[boot]\\nsystemd=true' to /etc/wsl.conf and run 'wsl --shutdown'."
           if detect_env() == "wsl" else "")
    return res("systemd", "systemd", WARN, "not running; flowguard start|stop|status supervisor is used", fix)


def check_python() -> Result:
    v = sys.version_info
    if v < (3, 10):
        return res("python", "System Python (core service)", FAIL, f"{v.major}.{v.minor}",
                   "sudo apt install python3 python3-venv (need >= 3.10).")
    return res("python", "System Python (core service)", PASS, f"{v.major}.{v.minor}.{v.micro}")


def check_python39() -> Result:
    p = shutil.which("python3.9")
    if not p:
        return res("python39", "Python 3.9 (Ryu engine)", FAIL, "python3.9 not found",
                   "Run scripts/setup_ubuntu.sh (adds the deadsnakes PPA).")
    return res("python39", "Python 3.9 (Ryu engine)", PASS, p)


def check_engine_venv() -> Result:
    py = REPO / ".venv-engine" / "bin" / "python"
    if not py.exists():
        return res("venv_engine", "Engine venv (.venv-engine)", FAIL, "missing",
                   "Run scripts/setup_ubuntu.sh.")
    rc, out = run([str(py), "-c",
                   "import ryu, eventlet, zmq, sys; from importlib.metadata import version as v; "
                   "print(sys.version.split()[0], 'ryu', v('ryu'), 'eventlet', v('eventlet'), 'pyzmq', v('pyzmq'))"])
    if rc != 0:
        return res("venv_engine", "Engine venv (.venv-engine)", FAIL, out.splitlines()[-1] if out else "import failed",
                   "Re-run scripts/setup_ubuntu.sh; pins are in requirements/engine.txt.")
    return res("venv_engine", "Engine venv (.venv-engine)", PASS, out)


def check_core_venv() -> Result:
    py = REPO / ".venv-core" / "bin" / "python"
    if not py.exists():
        return res("venv_core", "Core venv (.venv-core)", FAIL, "missing", "Run scripts/setup_ubuntu.sh.")
    rc, out = run([str(py), "--version"])
    return res("venv_core", "Core venv (.venv-core)", PASS if rc == 0 else FAIL, out)


def check_node() -> Result:
    node = shutil.which("node")
    if not node:
        return res("node", "Node.js (dashboard build)", WARN, "not installed (needed from Phase 3)",
                   "Run scripts/setup_ubuntu.sh (installs Node 20).")
    rc, out = run([node, "--version"])
    if not out.startswith("v20"):
        return res("node", "Node.js (dashboard build)", WARN, f"{out} (Node 20 is tested)")
    return res("node", "Node.js (dashboard build)", PASS, out)


def check_root() -> Result:
    if os.geteuid() == 0:
        return res("root", "Root / sudo ability", PASS, "running as root")
    rc, _ = run(["sudo", "-n", "true"])
    if rc == 0:
        return res("root", "Root / sudo ability", PASS, "passwordless sudo works")
    return res("root", "Root / sudo ability", FAIL, "not root and sudo needs a password",
               "Run as root, or configure sudo (the lab needs root for Mininet and OVS).")


def check_ovs_daemons() -> Result:
    missing = [d for d in ("ovsdb-server", "ovs-vswitchd") if run(["pgrep", "-x", d])[0] != 0]
    if shutil.which("ovs-vsctl") is None:
        return res("ovs", "Open vSwitch daemons", FAIL, "ovs-vsctl not installed",
                   "Run scripts/setup_ubuntu.sh (apt install openvswitch-switch).")
    if missing:
        return res("ovs", "Open vSwitch daemons", FAIL, "not running: " + ", ".join(missing),
                   "sudo systemctl enable --now openvswitch-switch   (or: sudo service openvswitch-switch start)")
    rc, out = run(["ovs-vsctl", "--timeout=5", "show"])
    if rc != 0:
        return res("ovs", "Open vSwitch daemons", FAIL, out.splitlines()[-1] if out else "ovs-vsctl failed",
                   "Check 'journalctl -u openvswitch-switch' or /var/log/openvswitch/.")
    ver = run(["ovs-vsctl", "--version"])[1].splitlines()[0]
    return res("ovs", "Open vSwitch daemons", PASS, ver)


def check_datapath() -> Result:
    """Report which OVS datapath is usable: kernel module or userspace (netdev)."""
    if Path("/sys/module/openvswitch").is_dir():
        return res("datapath", "OVS datapath mode", PASS, "kernel (openvswitch module loaded)")
    rc, out = run(["modprobe", "-n", "-v", "openvswitch"])
    if rc == 0:
        return res("datapath", "OVS datapath mode", WARN, "kernel module available but not loaded",
                   "sudo modprobe openvswitch")
    return res("datapath", "OVS datapath mode", WARN,
               "kernel module unavailable -> userspace datapath (datapath_type=netdev) must be used",
               "Expected on stock WSL2 kernels; FlowGuard falls back to netdev automatically. See docs/spike_findings.md.")


def check_ports() -> Result:
    busy = []
    for port, what in REQUIRED_PORTS.items():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                busy.append(f"{port} ({what})")
    if busy:
        return res("ports", "Required ports free", FAIL, "in use: " + ", ".join(busy),
                   "Find the owner with 'ss -ltnp' and stop it, or change ports in config.yaml.")
    return res("ports", "Required ports free", PASS, ", ".join(str(p) for p in REQUIRED_PORTS))


def check_disk() -> Result:
    free_gb = shutil.disk_usage(REPO).free / 1e9
    detail = f"{free_gb:.1f} GB free at {REPO}"
    if free_gb < MIN_DISK_GB_FAIL:
        return res("disk", "Disk space", FAIL, detail, "Free up disk space (>= 5 GB recommended).")
    if free_gb < MIN_DISK_GB_WARN:
        return res("disk", "Disk space", WARN, detail, ">= 5 GB recommended for sessions and models.")
    return res("disk", "Disk space", PASS, detail)


def _mininet_busy() -> bool:
    return run(["pgrep", "-f", "mininet:"])[0] == 0


def _mn_pingall(datapath: str) -> Tuple[bool, str]:
    cmd = ["mn", "--controller=none", f"--switch=ovsbr,datapath={datapath}", "--topo=single,3", "--test=pingall"]
    rc, out = run(cmd, timeout=120)
    ok = rc == 0 and "0% dropped" in out
    tail = [l for l in out.splitlines() if "dropped" in l or "rror" in l]
    return ok, (tail[-1] if tail else out[-160:])


def check_mininet() -> Result:
    if shutil.which("mn") is None:
        return res("mininet", "Mininet ping test", FAIL, "mn not installed",
                   "Run scripts/setup_ubuntu.sh (apt install mininet).")
    if os.geteuid() != 0 and run(["sudo", "-n", "true"])[0] != 0:
        return res("mininet", "Mininet ping test", SKIP, "needs root")
    if _mininet_busy():
        return res("mininet", "Mininet ping test", SKIP, "a Mininet lab is running; not disturbing it",
                   "Stop the lab and re-run to test.")
    outcomes = []
    for dp in ("kernel", "user"):
        ok, line = _mn_pingall(dp)
        outcomes.append((dp, ok, line))
        if ok:
            break
    run(["mn", "-c"], timeout=60)
    good = [dp for dp, ok, _ in outcomes if ok]
    if good:
        note = "" if good[0] == "kernel" else " (kernel datapath failed, userspace works)"
        return res("mininet", "Mininet ping test", PASS if good[0] == "kernel" else WARN,
                   f"pingall OK with datapath={good[0]}{note}",
                   "" if good[0] == "kernel" else "Use datapath=user (netdev). See docs/spike_findings.md.")
    detail = "; ".join(f"{dp}: {line}" for dp, _, line in outcomes)
    return res("mininet", "Mininet ping test", FAIL, detail[:300],
               "Check 'ovs-vsctl show', run 'mn -c', and see docs/spike_findings.md.")


CHECKS: List[Callable[[], Result]] = [
    check_environment, check_os, check_systemd, check_python, check_python39, check_engine_venv,
    check_core_venv, check_node, check_root, check_ovs_daemons, check_datapath, check_ports,
    check_disk, check_mininet,
]


def render(results: List[Result], color: bool) -> str:
    col = {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m", SKIP: "\033[90m"}
    reset = "\033[0m"
    wt = max(len(r["title"]) for r in results)
    lines = [f"{'STATUS':<6}  {'CHECK':<{wt}}  DETAIL", "-" * (wt + 40)]
    for r in results:
        s = r["status"]
        tag = f"{col[s]}{s:<6}{reset}" if color else f"{s:<6}"
        lines.append(f"{tag}  {r['title']:<{wt}}  {r['detail']}")
        if r["fix"] and s in (WARN, FAIL, SKIP):
            lines.append(f"{'':<6}  {'':<{wt}}  fix: {r['fix']}")
    counts = {k: sum(1 for r in results if r["status"] == k) for k in (PASS, WARN, FAIL, SKIP)}
    lines.append("-" * (wt + 40))
    lines.append("  ".join(f"{k}={v}" for k, v in counts.items()))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="FlowGuard environment doctor")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip the Mininet ping test")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for check in CHECKS:
        if args.quick and check is check_mininet:
            results.append(res("mininet", "Mininet ping test", SKIP, "skipped (--quick)"))
            continue
        try:
            results.append(check())
        except Exception as exc:  # a broken check must never hide the others
            results.append(res(check.__name__, check.__name__, FAIL, f"check crashed: {exc!r}"))

    if args.json:
        print(json.dumps({"env": detect_env(), "results": results}, indent=2))
    else:
        print(render(results, color=sys.stdout.isatty() and not args.no_color))
    return 1 if any(r["status"] == FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
