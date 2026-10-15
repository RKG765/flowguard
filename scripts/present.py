#!/usr/bin/env python3
"""Guided presentation demo: starts the lab + engine + core + dashboard on http://127.0.0.1:8787, creates the demo
admin, then walks the presenter through each step (what to click, what to say) and makes the same switch changes the
Phase 1 live tests make (tests/integration/test_l1_live.py), checking the engine's report after each one.

Run:  sudo make present      (or: sudo .venv-core/bin/python scripts/present.py)
Local lab only: every change goes to the Mininet switch s1 that this script starts and removes again.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8787"
DATA = "/tmp/flowguard-demo"
LOG = REPO / "data" / "run" / "present-stack.log"
ADMIN = {"username": "admin", "password": "flowguard-demo"}
DPID = "0000000000000001"
ACL = "table=0,priority=100,tcp,tp_dst=23"

B, G, Y, R, C, D, X = "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[2m", "\033[0m"
stack = None
token = None


# ---- small helpers -------------------------------------------------------------------------------------------------
def say(text):
    print(f"   {C}Bolo:{X} {text}")


def show(text):
    print(f"   {Y}Dikhao:{X} {text}")


def title(n, text):
    print(f"\n{B}{'=' * 78}\n STEP {n}: {text}\n{'=' * 78}{X}")


def pause(msg="Ho gaya? Agle step ke liye Enter dabao"):
    try:
        return input(f"\n   {D}>> {msg}...{X} ").strip().lower()
    except EOFError:
        return ""


def api(method, path, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(URL + path, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


def ofctl(*args):
    return subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", *args], capture_output=True, text=True)


def print_table0(label):
    print(f"   {D}switch s1, table 0 ({label}):{X}")
    for line in ofctl("dump-flows", "s1", "table=0").stdout.splitlines():
        if "priority=" not in line:
            continue
        parts = [p.strip() for p in line.replace(" actions=", ", actions=").split(",")]
        keep = [p for p in parts if p.startswith(("cookie", "priority", "tcp", "arp", "tp_dst", "actions"))
                or p in ("tcp", "arp")]
        print(f"     {D}{', '.join(keep)}{X}")


def wait_for(fn, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def new_alert(kind, since):
    code, body = api("GET", f"/api/alerts?kind={kind}&since={since - 1}")
    items = (body or {}).get("items", []) if code == 200 else []
    return items[0] if items else None


def bad_rules():
    code, rows = api("GET", f"/api/rules?dpid={DPID}")
    return [r for r in (rows or []) if r.get("status") not in ("ok", "pending")] if code == 200 else []


def summary():
    code, body = api("GET", "/api/rules/summary")
    return body if code == 200 else {}


# ---- stack ---------------------------------------------------------------------------------------------------------
def cleanup_lab():
    subprocess.run(["pkill", "-f", "[e]2e_live/stack.py"], capture_output=True)
    time.sleep(1)
    subprocess.run(["pkill", "-f", "[r]yu-manager"], capture_output=True)
    subprocess.run(["mn", "-c"], capture_output=True)


def start(mode):
    global stack, token
    token = None
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "w")
    print(f"   {D}lab + engine + core start ho rahe hain (mode: {mode}), 30-60 second lagenge ...{X}")
    stack = subprocess.Popen([str(REPO / ".venv-core/bin/python"), str(REPO / "tests/e2e_live/stack.py"),
                              "--core-port", "8787", "--response-mode", mode, "--data", DATA],
                             cwd=str(REPO), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    ready = wait_for(lambda: "FLOWGUARD-STACK-READY" in LOG.read_text(errors="ignore").splitlines(), 150, 1)
    if not ready:
        print(f"{R}   Stack ready nahi hua. Log: {LOG}{X}")
        stop()
        sys.exit(1)
    api("POST", "/api/setup", ADMIN)
    code, body = api("POST", "/api/auth/login", ADMIN)
    if code != 200:
        print(f"{R}   Admin login nahi hua (HTTP {code}). Log: {LOG}{X}")
        stop()
        sys.exit(1)
    token = body["token"]
    ok = wait_for(lambda: summary().get("verified") == 3, 30)
    s = summary()
    print(f"   {G}READY:{X} {s.get('verified', '?')}/{s.get('protected', '?')} rules verified, mode = {mode}")
    if not ok:
        print(f"   {Y}(rules abhi verify ho rahe hain, 10 second mein dashboard refresh karna){X}")


def stop():
    global stack
    if stack and stack.poll() is None:
        os.killpg(stack.pid, signal.SIGINT)
        try:
            stack.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(stack.pid, signal.SIGKILL)
    stack = None
    cleanup_lab()


def login_box():
    print(f"\n   {B}Browser (Windows ka Chrome/Edge bhi chalega):{X} {URL}")
    print(f"   {B}Login:{X} username {G}{ADMIN['username']}{X}   password {G}{ADMIN['password']}{X}")


# ---- one tamper scenario (alert-only mode) -------------------------------------------------------------------------
def scenario(n, name, kind, change, story, where):
    title(n, name)
    print_table0("pehle")
    pause("Ready ho to Enter dabao, change switch par hoga")
    t0 = time.time()
    p = ofctl(*change)
    if p.returncode != 0:
        print(f"{R}   ovs-ofctl fail: {p.stderr.strip()}{X}")
        return
    print(f"   {R}Change ho gaya:{X} {story}")
    a = wait_for(lambda: new_alert(kind, t0), 10)
    if a:
        lat = a.get("detect_latency_ms")
        print(f"   {G}ENGINE NE PAKDA:{X} {a['kind'].upper()} (priority {a.get('priority')}), "
              f"detect {lat if lat is not None else '?'} ms, severity {a.get('severity')}")
    else:
        print(f"   {Y}Alert abhi API mein nahi dikha; dashboard dekho (Live Detection).{X}")
    print_table0("ab, tampered")
    for line in where:
        show(line)
    say("Rule controller ke bahar se badla gaya. Signature match nahi hua, isliye FlowGuard ne turant pakda. "
        "Alert-only mode mein woh khud kuch nahi badalta; admin dekh kar Repair karta hai.")
    while True:
        ans = pause("Dashboard se Repair karke Enter dabao  (r = script se repair, s = skip)")
        if ans == "r":
            for row in bad_rules():
                api("POST", "/api/rules/repair", {"dpid": DPID, "table_id": row["table_id"],
                                                  "priority": row["priority"], "match": row.get("match", {})})
            print(f"   {D}repair request bheja, engine ka wait ...{X}")
        if ans == "s":
            break
        if wait_for(lambda: not bad_rules(), 8 if ans == "r" else 3):
            print(f"   {G}REPAIRED:{X} switch phir se signed policy jaisa hai.")
            print_table0("repair ke baad")
            show("Alerts page: yeh incident 'removed/restored' ke saath. Acknowledge / Assign / Note karke dikhao.")
            break
        print(f"   {Y}Abhi bhi tampered hai. Rules page > rule par click > 'Repair this rule' > 'Repair now'.{X}")
    pause()


# ---- the walkthrough ------------------------------------------------------------------------------------------------
def main():
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "-E", str(REPO / ".venv-core/bin/python"), *sys.argv])
    for v in (".venv-core", ".venv-engine"):
        if not (REPO / v / "bin/python").exists():
            sys.exit(f"{v} missing: run once  sudo bash scripts/setup_ubuntu.sh")
    if not (REPO / "web/dist/index.html").exists():
        sys.exit("web/dist missing: run once  make build-web  (see RUN_AND_SHOW.md)")
    signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(0)))

    print(f"{B}\n FlowGuard presentation demo{X}  (kabhi bhi Ctrl+C = sab band)\n")
    cleanup_lab()
    start("alert_only")
    login_box()

    title(1, "Overview: system ki health")
    show("Overview page: 'Engine connected - monitor up', L1 active, L2/L3 planned.")
    say("Ek command se asli Open vSwitch switch, 4 Mininet hosts, Ryu controller ke saath FlowGuard engine, "
        "FastAPI core aur yeh dashboard chal rahe hain. Koi simulation nahi.")
    pause()

    title(2, "Rules: signed rules (project ka main idea)")
    show("Rules page: 3 rules, sab VERIFIED. Telnet (tcp_dst=23, drop) wale rule par click karo.")
    show("Right side: 'Signed by the controller' vs 'On the switch now' - dono same.")
    say("Har rule ka HMAC-SHA256 signature uske cookie mein hai, switch id aur key epoch se bound. "
        "Rule 1: Telnet block. Rule 2: SSH allow. Rule 3: baaki sab normal switching (table 1).")
    pause()

    title(3, "Topology")
    show("Topology page: FlowGuard engine -> switch s1 (green) -> 4 hosts (port 1-4).")
    say("Hosts manually nahi likhe; table 1 ka learning switch traffic se unke MAC seekhta hai.")
    pause()

    scenario(4, "Attack 1: Telnet block rule ko 'allow' bana dena (ALTERED)", "altered",
             ["--strict", "mod-flows", "s1", f"{ACL},actions=output:1"],
             "Telnet rule ka action 'drop' se 'output:1' (allow) kar diya.",
             ["Live Detection: 'altered' item, click karo - What happened + timeline.",
              "Rules: 'Altered (1)' chip > rule > Signed 'drop' vs On switch 'output:1'."])

    scenario(5, "Attack 2: fake rule daalna (FORGED)", "forged",
             ["add-flow", "s1", "table=0,priority=300,arp,actions=drop"],
             "Bina signature ka naya rule (priority 300) daala.",
             ["Live Detection: 'forged - priority 300' item.",
              "Rules: 'Forged (1)' > rule > 'No signed rule exists for this slot'."])

    scenario(6, "Attack 3: security rule delete karna (MISSING)", "missing",
             ["--strict", "del-flows", "s1", ACL],
             "Telnet block rule hi delete kar diya.",
             ["Rules: 'Missing (1)' - rule switch se gayab hai.",
              "Repair ke baad rule apne ORIGINAL cookie (signature) ke saath wapas aata hai."])

    title(7, "Sahi raste se naya rule: zero false alarm")
    before = (api("GET", "/api/alerts")[1] or {}).get("total", 0)
    pol = Path(DATA) / "policy.yaml"
    pause("Enter dabao: policy file mein HTTP (port 80) block rule add hoga")
    text = pol.read_text()
    if "tcp_dst: 80" not in text:
        pol.write_text(text.rstrip("\n") + "\n  - {table: 0, priority: 95, match: {eth_type: 0x0800, ip_proto: 6, "
                       "tcp_dst: 80}, instructions: []}\n")
    ok = wait_for(lambda: summary().get("verified") == 4, 15)
    after = (api("GET", "/api/alerts")[1] or {}).get("total", 0)
    print(f"   {G if ok else Y}Rules verified: {summary().get('verified')}{X}, naye alerts: {after - before}")
    show("Rules page: ab 4 rules, sab VERIFIED (naya: tcp_dst=80, drop).")
    say("Admin ne policy controller ke through badli: engine ne naya rule khud sign karke daala, aur koi alert "
        "nahi aaya. Sahi badlaav = zero false alarm, galat badlaav = turant pakda.")
    pause()

    title(8, "Automatic repair mode (milliseconds mein)")
    print(f"   {D}Ab engine ko 'restore' mode mein restart karenge: khud repair karega.{X}")
    pause("Enter dabao (restart ~1 minute)")
    stop()
    cleanup_lab()
    start("restore")
    login_box()
    show("Browser mein page refresh karo aur dobara login karo (naya lab = naya data).")
    pause("Login ho gaya? Enter dabao: Telnet rule phir se badla jayega")
    t0 = time.time()
    ofctl("--strict", "mod-flows", "s1", f"{ACL},actions=output:1")
    a = wait_for(lambda: new_alert("altered", t0), 10)
    time.sleep(1)
    if a:
        print(f"   {G}PAKDA AUR KHUD THEEK KIYA:{X} detect {a.get('detect_latency_ms')} ms, "
              f"restore {a.get('time_to_restore_ms')} ms, action = {a.get('action')}")
    print_table0("1 second baad")
    show("Alerts page: 'altered - restored' incident, timing ke saath. Rules page: sab VERIFIED hi dikh raha hai.")
    say("Itna fast theek hua ki rule page par kabhi galat dikha hi nahi; saboot Alerts aur Live Detection mein hai.")
    pause()

    title(9, "Khatam")
    say("Yahi saare scenarios (aur 11 aur) 19 automated live tests mein har baar check hote hain: sudo make test-live")
    pause("Enter dabao: sab band ho jayega")
    stop()
    print(f"\n{G} Demo band. Dobara chalane ke liye: sudo make present{X}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{D}   band ho raha hai ...{X}")
        stop()
