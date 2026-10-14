"""Live L1 lab: real Open vSwitch + Mininet + the real engine (Ryu) process. Needs root. Run in .venv-core."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "topo"))

DPID = "0000000000000001"
OF = "OpenFlow13"
FLOW_RE = re.compile(r"cookie=(0x[0-9a-f]+).*?table=(\d+).*?priority=(\d+)(?:,(\S+))? actions=(.*)$")


def _need_root():
    if os.geteuid() != 0:
        pytest.skip("integration tests need root (Mininet/OVS)")
    if not (REPO / ".venv-engine/bin/ryu-manager").exists():
        pytest.skip("engine venv missing: run scripts/setup_ubuntu.sh")
    if shutil.which("ovs-vsctl") is None:
        pytest.skip("Open vSwitch not installed")


def ofctl(*args, check=True):
    p = subprocess.run(["ovs-ofctl", "-O", OF, *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"ovs-ofctl {args}: {p.stderr}")
    return p.stdout


def dump(table=0):
    """Rules in a table as dicts: cookie(int), priority, match(str), actions(str)."""
    rows = []
    for line in ofctl("dump-flows", "s1", f"table={table}").splitlines():
        m = FLOW_RE.search(line)
        if m:
            rows.append({"cookie": int(m.group(1), 16), "table": int(m.group(2)), "priority": int(m.group(3)),
                         "match": m.group(4) or "", "actions": m.group(5)})
    return rows


def find_rule(table, priority, match_contains=""):
    return next((r for r in dump(table) if r["priority"] == priority and match_contains in r["match"]), None)


class Lab:
    def __init__(self, data: Path, policy: Path, key: Path):
        self.data, self.policy, self.key = data, policy, key
        self.spool = data / "spool" / "alerts.jsonl"
        self.events = data / "run" / "engine_events.jsonl"
        self.status = data / "run" / "engine_status.json"
        self.control = data / "run" / "control"
        self.ryu = None
        self.net = None

    def alerts(self, since=0.0, kind=None):
        out = []
        if self.spool.exists():
            for line in self.spool.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") == "alert" and r["t"] >= since and (kind is None or r["kind"] == kind):
                    out.append(r)
        return out

    def updates(self, alert_id):
        out = []
        for line in self.spool.read_text().splitlines():
            r = json.loads(line)
            if r.get("type") == "alert_update" and r.get("alert_id") == alert_id:
                out.append(r)
        return out

    def wait(self, pred, timeout=6.0, interval=0.05):
        end = time.time() + timeout
        while time.time() < end:
            v = pred()
            if v:
                return v
            time.sleep(interval)
        return None

    def wait_alert(self, kind, since, timeout=6.0):
        return self.wait(lambda: (self.alerts(since, kind) or [None])[0], timeout)

    def engine_status(self):
        try:
            return json.loads(self.status.read_text())
        except (OSError, ValueError):
            return {}

    def settle(self, seconds=1.2):
        time.sleep(seconds)

    def ryu_log(self):
        return (self.data / "ryu.log").read_text()[-3000:] if (self.data / "ryu.log").exists() else ""


DEFAULT_POLICY = """\
rules:
  - {table: 0, priority: 100, match: {eth_type: 0x0800, ip_proto: 6, tcp_dst: 23}, instructions: []}
  - {table: 0, priority: 90, match: {eth_type: 0x0800, ip_proto: 6, tcp_dst: 22}, instructions: [{type: goto_table, table_id: 1}]}
  - {table: 0, priority: 0, match: {}, instructions: [{type: goto_table, table_id: 1}]}
"""


def start_engine(data: Path, policy: Path, key: Path, extra_env=None):
    env = dict(os.environ, PYTHONPATH=str(REPO), FLOWGUARD_DATA_DIR=str(data), FLOWGUARD_KEY_FILE=str(key),
               FLOWGUARD_POLICY=str(policy), FLOWGUARD_GRACE_MS="300", FLOWGUARD_RECONCILE_S="2",
               FLOWGUARD_CONFIG=str(data / "no-config.yaml"))
    env.pop("FLOWGUARD_HMAC_KEY", None)
    env.update(extra_env or {})
    log = open(data / "ryu.log", "w")
    return subprocess.Popen([str(REPO / ".venv-engine/bin/ryu-manager"), "--ofp-tcp-listen-port", "6653", "engine.app"],
                            cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT)


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    _need_root()
    import topo_basic
    from engine.crypto import generate_key_file
    subprocess.run(["mn", "-c"], capture_output=True)
    data = tmp_path_factory.mktemp("fgdata")
    key = data / "keys" / "hmac.key"
    generate_key_file(str(key))
    policy = data / "policy.yaml"
    policy.write_text(DEFAULT_POLICY)
    lab = Lab(data, policy, key)
    lab.ryu = start_engine(data, policy, key)
    time.sleep(3)
    net, info = topo_basic.build_net("auto", False, "127.0.0.1", 6653, protocols="OpenFlow10,OpenFlow13", listen_port=6634)
    lab.net = net
    try:
        net.start()
        ready = lab.wait(lambda: lab.engine_status().get("ready", {}).get(DPID), timeout=25)
        if not ready:
            pytest.fail(f"engine never became ready\n{lab.ryu_log()}")
        lab.settle(1.0)
        yield lab
    finally:
        net.stop()
        lab.ryu.terminate()
        try:
            lab.ryu.wait(timeout=8)
        except subprocess.TimeoutExpired:
            lab.ryu.kill()
        subprocess.run(["mn", "-c"], capture_output=True)
