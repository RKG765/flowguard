"""Phase 7 least privilege on the real lab: the engine and the core run as their own unprivileged accounts (only Mininet / Open
vSwitch stays root). Checks the privilege split itself (who runs, who can read the signing key and the user database) and that
the product still works across it: alert delivery engine to core, and the core's control files (key rotation, policy hand-off)
read by the engine. Switch changes use the lab's own `ovs-ofctl`, like the other live tests."""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from conftest import REPO, _need_root, ofctl

DATA = Path("/run/flowguard/test-least-privilege")
PORT = 18790
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = {"username": "admin", "password": "least-privilege-pass-1"}


def as_user(user, *cmd):
    return subprocess.run(["runuser", "-u", user, "--", *cmd], capture_output=True, text=True)


def wait(pred, timeout=15.0, interval=0.2):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    return None


@pytest.fixture(scope="module")
def stack():
    _need_root()
    subprocess.run(["bash", str(REPO / "scripts" / "service-users.sh")], check=True, capture_output=True)
    os.makedirs("/run/flowguard", exist_ok=True)
    os.chmod("/run/flowguard", 0o755)
    proc = subprocess.Popen([sys.executable, str(REPO / "tests" / "e2e_live" / "stack.py"), "--core-port", str(PORT), "--response-mode", "restore",
                             "--data", str(DATA), "--drop-privileges"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO))
    ready = False
    end = time.time() + 90
    out = []
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            break
        out.append(line)
        if "FLOWGUARD-STACK-READY" in line:
            ready = True
            break
    if not ready:
        proc.terminate()
        pytest.fail("stack never became ready:\n" + "".join(out[-30:]))
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        subprocess.run(["mn", "-c"], capture_output=True)


@pytest.fixture(scope="module")
def api(stack):
    c = httpx.Client(base_url=BASE, timeout=10)
    assert wait(lambda: c.get("/api/health").status_code == 200, 30)
    assert c.post("/api/setup", json=ADMIN).status_code == 201
    tok = c.post("/api/auth/login", json=ADMIN).json()["token"]
    c.cookies.clear()
    c.headers["Authorization"] = f"Bearer {tok}"
    yield c
    c.close()


def test_engine_and_core_run_as_their_own_unprivileged_accounts(stack):
    ps = subprocess.run(["ps", "-eo", "user:30,args"], capture_output=True, text=True).stdout.splitlines()
    engine = [ln for ln in ps if "ryu-manager" in ln and "engine.app" in ln]
    core = [ln for ln in ps if "core.main:create_app" in ln and str(PORT) in ln]
    assert engine and engine[0].split()[0] == "flowguard-engine", engine
    assert core and core[0].split()[0] == "flowguard-core", core


def test_the_signing_key_and_the_user_database_are_each_private_to_one_account(stack):
    key, db = DATA / "keys" / "hmac.key", DATA / "core" / "core.db"
    assert (key.stat().st_mode & 0o777) == 0o600 and key.owner() == "flowguard-engine"
    assert as_user("flowguard-engine", "head", "-c", "4", str(key)).returncode == 0
    assert as_user("flowguard-core", "head", "-c", "4", str(key)).returncode != 0, "the core must never be able to read the signing key"
    assert as_user("flowguard-core", "head", "-c", "4", str(db)).returncode == 0
    assert as_user("flowguard-engine", "head", "-c", "4", str(db)).returncode != 0, "the engine must never be able to read the user database"
    assert as_user("flowguard-core", "ls", str(DATA / "engine")).returncode != 0, "the golden store is the engine's alone"


def test_a_tampered_rule_is_detected_repaired_and_reported_across_the_privilege_split(stack, api):
    t0 = time.time()
    ofctl("add-flow", "s1", "table=0,priority=300,arp,actions=drop")
    got = wait(lambda: [a for a in api.get("/api/alerts", params={"kind": "forged"}).json()["items"] if a["t"] >= t0 - 1], 20)
    assert got and got[0]["action"] == "removed"
    assert got[0]["detected_by"] == "monitor_event", "the unprivileged engine must keep the live change monitor, not fall back to the poll"
    assert wait(lambda: any(((api.get("/api/engine/status").json().get("status") or {}).get("monitors_up") or {}).values()), 20), "monitor session must be up"
    assert wait(lambda: "priority=300" not in ofctl("dump-flows", "s1", "table=0"), 10), "the unprivileged engine must still repair the switch"


def test_the_cores_control_files_reach_the_engine(stack, api):
    assert api.post("/api/engine/rotate-key").status_code == 202
    assert wait(lambda: api.get("/api/engine/status").json().get("status", {}).get("epoch") == 2, 20), "the engine must read the core's rotate request"
    policy = {"dry_run": False, "response_mode": "restore", "critical_tables": [0], "weights": {"l1": 1.0, "l2": 0.8, "l3": 0.4},
              "thresholds": {"alert": 0.3, "restore": 0.5, "quarantine": 0.8},
              "actions": {"critical": "restore_and_alert", "high": "restore_and_alert", "medium": "alert_only", "low": "alert_only"}}
    assert api.put("/api/policies", json=policy).status_code == 200
    assert wait(lambda: api.get("/api/engine/status").json().get("status", {}).get("risk_dry_run") is False, 20), "the engine must read the core's policy"
