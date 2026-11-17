"""FlowGuard operator console (Streamlit). A second front end over the same core API the React dashboard uses.

Run (with `sudo make demo` or `sudo make present` already running):  make ui   ->  http://127.0.0.1:8501
Local-only console: it listens on 127.0.0.1 and signs in to the local core automatically (FG_USER / FG_PASSWORD,
default: the demo account `make present` creates). Read-only monitoring plus the operator actions the API allows (acknowledge, incidents, admin repair, users, key
rotation). Like the main dashboard it has no attack execution (ADR-019). L2 probes and L3 ML are Phase 5 placeholders.
"""
import hashlib
import html
import json
import os
import random
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

CORE = os.environ.get("FG_CORE_URL", "http://127.0.0.1:8787")
KINDS = ["altered", "forged", "missing", "shadow", "unattributed_change"]
STATUS_ICON = {"ok": "\u25cf verified", "altered": "! altered", "forged": "\u00d7 forged", "missing": "\u2205 missing",
               "shadow": "\u2248 shadow", "pending": "\u00b7 pending"}

st.set_page_config(page_title="FlowGuard", page_icon="\u25a4", layout="wide")


# ---- API -----------------------------------------------------------------------------------------------------------
def esc(v):
    """Everything that comes from the API and is placed in HTML goes through this."""
    return html.escape(str(v))


def api(method, path, **kw):
    headers = {}
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        r = requests.request(method, CORE + path, headers=headers, timeout=6, **kw)
    except requests.RequestException as e:
        return 0, str(e)
    if r.status_code == 401 and st.session_state.get("token"):
        st.session_state.pop("token", None)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


def get(path, default=None):
    code, body = api("GET", path)
    return body if code == 200 else default


def ts(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "-"


def fmt_match(m):
    return ", ".join(f"{k}={hex(v) if k == 'eth_type' and isinstance(v, int) else v}" for k, v in (m or {}).items()) or "any packet"


def fmt_instr(ins):
    if ins is None:
        return "-"
    if not ins:
        return "drop"
    out = []
    for i in ins:
        if i.get("type") == "goto_table":
            out.append(f"goto_table:{i.get('table_id')}")
        elif i.get("type") == "apply_actions":
            out.append(", ".join(f"{a.get('type')}:{a.get('port', '')}".rstrip(":") for a in i.get("actions", [])))
        else:
            out.append(json.dumps(i))
    return "; ".join(out)


WIRE = ["#3b82c4", "#f08a24", "#3fae5a", "#8a5a3c", "#7b8794", "#d6453d", "#8e63c9", "#e6c229", "#ece8dc", "#e57fa3", "#34b5b0", "#2b2f36"]
PORT_PATH = {  # drawn icons (24x24 strokes), never text glyphs
    "ok": "M5 12l4.5 4.5L19 7",
    "altered": "M12 4l9 16H3z M12 10v4 M12 17v.5",
    "forged": "M6 6l12 12 M18 6L6 18",
    "shadow": "M12 4l9 5-9 5-9-5z M3 14l9 5 9-5",
    "missing": "M12 4a8 8 0 100 16 8 8 0 000-16z M5.5 5.5l13 13",
    "pending": "M12 3a9 9 0 100 18 9 9 0 000-18z M12 7v5l3 2",
}
PORT = {k: ({"ok": "ok", "altered": "bad", "forged": "bad", "shadow": "bad", "missing": "miss", "pending": "pend"}[k], PORT_PATH[k]) for k in PORT_PATH}


def _bands(cookie):
    if not cookie:
        return None
    h = "".join(c for c in str(cookie).lower().replace("0x", "") if c in "0123456789abcdef").rjust(16, "0")[-16:]
    return [int(h[i * 2:i * 2 + 2], 16) % len(WIRE) for i in range(8)]


def stripe(cookie, against="__none__"):
    """Signature move: the 8-byte HMAC cookie as 8 wire-code bands. With `against`, bands that differ are hatched."""
    b = _bands(cookie)
    if b is None:
        return '<span class="fg-mono">no tag</span>'
    ref = None if against == "__none__" else _bands(against)
    return '<span class="fg-stripe">' + "".join(
        f'<i class="{"diff" if ref is not None and ref[k] != v else ""}" style="background:{WIRE[v]}"></i>'
        for k, v in enumerate(b)) + "</span>"


def port_strip(statuses):
    cells = "".join(
        f'<span class="fg-port {PORT.get(x, ("pend", PORT_PATH["pending"]))[0]}" title="{esc(x)}">'
        f'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{PORT.get(x, ("pend", PORT_PATH["pending"]))[1]}"/></svg></span>'
        for x in statuses)
    return f'<div class="fg-ports">{cells}</div>'



# ---- look ----------------------------------------------------------------------------------------------------------
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600&family=JetBrains+Mono:wght@400;600&display=swap');
  html, body, [class*="css"], .stMarkdown, .stButton button {font-family: 'Barlow', 'Segoe UI', system-ui, sans-serif;}
  code, pre, .fg-mono {font-family: 'JetBrains Mono', ui-monospace, monospace !important;}
  .block-container {padding-top: 3.4rem; max-width: 1400px;}
  [data-testid="stDecoration"] {display: none;}
  h1, h2, h3, h4 {font-family: 'Barlow Condensed', 'Barlow', sans-serif; text-transform: uppercase; letter-spacing: .08em;}
  [data-testid="stSidebar"] {background: #182436; border-right: 1px solid #0f1826;}
  [data-testid="stSidebar"] * {color: #dfe6f0;}
  [data-testid="stSidebar"] label p {font-size: 1rem;}
  [data-testid="stMetric"] {background: #252522; border: 1px solid #4E4D46; border-top: 3px solid #4E4D46; border-radius: 4px; padding: 12px 16px;}
  [data-testid="stMetricLabel"] p {color: #A6A49C; font: 600 .85rem 'Barlow Condensed', sans-serif; text-transform: uppercase; letter-spacing: .1em;}
  [data-testid="stMetricValue"] {font-family: 'JetBrains Mono', monospace; font-size: 1.9rem;}
  .fg-brand {display:flex; align-items:center; gap:10px; margin-bottom: 6px;}
  .fg-brand b {font: 600 1.35rem 'Barlow Condensed', sans-serif; letter-spacing: .1em; text-transform: uppercase; color:#fff;}
  .fg-wire {display:inline-flex; gap:3px; padding:5px 6px; border:1.5px solid #e6ebf2; border-radius:3px;}
  .fg-wire i {display:block; width:5px; height:12px; border-radius:1px;}
  .fg-bar {display:flex; align-items:center; justify-content:space-between; gap:16px; padding:10px 16px; margin-bottom:16px;
           background:#252522; border:1px solid #4E4D46; border-top: 3px solid #5EB0E8; border-radius:4px;}
  .fg-bar h1 {font-size: 1.5rem; margin: 0; color: #ECE8DC; padding: 0;}
  .fg-bar p {margin: 0; color: #A6A49C; font-size: .9rem;}
  .fg-pill {padding: 4px 12px; border-radius: 3px; font: 600 .9rem 'Barlow Condensed', sans-serif; letter-spacing: .08em; text-transform: uppercase; white-space: nowrap;}
  .fg-ok {background:#13301f; color:#8fe0a8; border:1px solid #5ECC80;}
  .fg-warn {background:#3a2a0c; color:#f9c877; border:1px solid #F6AA38;}
  .fg-bad {background:#44161a; color:#ffb0b0; border:1px solid #FF7070;}
  .fg-card {background:#252522; border:1px solid #4E4D46; border-top: 3px solid #4E4D46; border-radius:4px; padding:14px 16px; height:100%;}
  .fg-card h4 {margin:0 0 6px 0; font-size:1.05rem;}
  .fg-card p {margin:0; color:#A6A49C; font-size:.92rem;}
  .fg-ports {display:flex; flex-wrap:wrap; gap:4px; margin: 6px 0 14px 0;}
  .fg-port {width:24px; height:24px; display:grid; place-items:center; border-radius:3px; border:1px solid; font: 600 .8rem 'JetBrains Mono', monospace;}
  .fg-port.ok {background:#1c4a2c; border-color:#5ECC80; color:#8fe0a8;}
  .fg-port.bad {background:#5a1f25; border-color:#FF7070; color:#ffb0b0;}
  .fg-port.miss {background:#5a3a0c; border-color:#F6AA38; color:#f9c877;}
  .fg-port.pend {background:#1d3a52; border-color:#7EC4F0; color:#a9d8f5;}
  .fg-stripe {display:inline-flex; vertical-align:middle; height:16px; border:1px solid #4E4D46; border-radius:2px; overflow:hidden;}
  .fg-stripe i {display:block; width:7px; position:relative;}
  .fg-stripe i.diff::after {content:''; position:absolute; left:0; right:0; bottom:0; height:5px; background:repeating-linear-gradient(135deg,#000 0 2px,#fff 2px 4px);}
  [data-testid="stAlert"] p, [data-testid="stAlert"] li {color: #ECE8DC !important;}
  [data-testid="stAlert"] {background: #252522; border: 1px solid #4E4D46;}
</style>
""", unsafe_allow_html=True)


# ---- automatic local sign-in (no login screen) ----------------------------------------------------------------------
# The console only listens on 127.0.0.1 and signs in to the local core with the demo account that `make present`
# creates. Override with FG_USER / FG_PASSWORD if the lab admin was created with other credentials.
DEMO_USER = os.environ.get("FG_USER", "admin")
DEMO_PASSWORD = os.environ.get("FG_PASSWORD", "flowguard-demo")


def auto_sign_in():
    code, _ = api("GET", "/api/health")
    if code != 200:
        st.markdown("## FlowGuard")
        st.warning(f"Waiting for the FlowGuard core at {CORE} ...")
        st.markdown("The lab is not running yet. In **another terminal** start it (this page connects by itself "
                    "within a few seconds, no refresh needed):")
        st.code("cd ~/flowguard && sudo make present", language="bash")
        time.sleep(3)
        st.rerun()
    if (get("/api/setup/status") or {}).get("needs_setup"):
        api("POST", "/api/setup", json={"username": DEMO_USER, "password": DEMO_PASSWORD})
    c, b = api("POST", "/api/auth/login", json={"username": DEMO_USER, "password": DEMO_PASSWORD})
    if c != 200:
        st.error(f"Automatic sign-in as '{DEMO_USER}' failed. Start the console with the lab admin's credentials:  "
                 "`FG_USER=<name> FG_PASSWORD=<password> make ui`")
        st.stop()
    st.session_state.token = b["token"]


if not st.session_state.get("token"):
    auto_sign_in()
me = get("/api/auth/me") or {}
if not me:
    auto_sign_in()
    me = get("/api/auth/me") or {}
role = me.get("role", "viewer")
is_admin, is_analyst = role == "admin", role in ("admin", "analyst")


# ---- sidebar -------------------------------------------------------------------------------------------------------
NAV = ["Overview", "Rules", "Live Detection", "Demo Lab (simulated)", "Alerts & Incidents", "Topology", "Policy",
       "Reports", "Audit log", "Engine", "Users", "L2 Probes / L3 ML"]
with st.sidebar:
    st.markdown('<div class="fg-brand"><span class="fg-wire"><i style="background:#3b82c4"></i><i style="background:#f08a24"></i>'
                '<i style="background:#3fae5a"></i><i style="background:#d6453d"></i></span><b>FlowGuard</b></div>', unsafe_allow_html=True)
    st.caption("SDN flow-rule integrity \u00b7 operator console")
    page = st.radio("Navigate", NAV, label_visibility="collapsed")
    st.divider()
    st.caption(f"Local console · {me.get('username')} ({role}) · core {CORE}")


def engine_banner():
    eng = get("/api/engine/status") or {}
    sws = get("/api/switches") or []
    if not eng.get("known"):
        pill = '<span class="fg-pill fg-warn">Engine has not reported yet</span>'
    elif eng.get("stale"):
        pill = f'<span class="fg-pill fg-bad">Engine not reporting ({eng.get("age_seconds")} s)</span>'
    else:
        up = all(s.get("connected") and s.get("monitor_up") for s in sws) and sws
        mode = (eng.get("status") or {}).get("response_mode", "?")
        pill = (f'<span class="fg-pill {"fg-ok" if up else "fg-warn"}">● Engine connected · monitor '
                f'{"up" if up else "DOWN"} · {mode}</span>')
    st.markdown(f'<div class="fg-bar"><div><h1>{page}</h1><p>FlowGuard · signed flow rules, '
                f'verified live on the switch</p></div>{pill}</div>', unsafe_allow_html=True)
    return eng, sws


# ---- pages ---------------------------------------------------------------------------------------------------------
@st.fragment(run_every=3)
def overview():
    eng, sws = engine_banner()
    s = get("/api/rules/summary") or {}
    rep = get("/api/reports/summary") or {}
    all_rules = get("/api/rules") or []
    st.markdown("#### Patch panel: one port per rule on the switch")
    if all_rules:
        st.markdown(port_strip([r["status"] for r in all_rules]), unsafe_allow_html=True)
    else:
        st.caption("Ports appear after the engine's first verification pass.")
    c = st.columns(5)
    c[0].metric("Protected rules", s.get("protected", 0))
    c[1].metric("Verified", f"{s.get('verified', 0)} of {s.get('protected', 0)}", help=f"{s.get('verified_percent', 0)}% of the signed rules match the switch")
    c[2].metric("Not OK now", sum((s.get("by_status") or {}).get(k, 0) for k in ("altered", "forged", "missing", "shadow")))
    c[3].metric("Alerts (total)", rep.get("alerts_total", 0))
    c[4].metric("Open incidents", rep.get("open_incidents", 0))
    st.subheader("Detection layers")
    l = st.columns(3)
    for col, (name, text, cls) in zip(l, [
            ("L1 · Signed-rule verification", "HMAC-signed rules checked on every switch change", "fg-ok"),
            ("L2 · Data-plane probes", "Canary packets check that signed rules forward as signed", "fg-ok" if (get("/api/probes?limit=1") or {}).get("available") else "fg-warn"),
            ("L3 · Anomaly scoring", "Baseline learned from normal rule churn scores each change", "fg-ok" if (get("/api/ml/scores?limit=1") or {}).get("available") else "fg-warn")]):
        status = "active" if cls == "fg-ok" else "waiting"
        col.markdown(f'<div class="fg-card"><h4>{name}</h4><p>{text}</p><br><span class="fg-pill {cls}">{status}</span>'
                     '</div>', unsafe_allow_html=True)
    st.subheader("Live feed (latest alerts)")
    items = (get("/api/alerts?limit=10") or {}).get("items", [])
    if items:
        st.dataframe(pd.DataFrame([{"time": ts(a["t"]), "kind": a["kind"], "severity": a["severity"], "priority": a["priority"],
                                    "action": a["action"], "detect ms": a["detect_latency_ms"], "summary": a["summary"]}
                                   for a in items]), hide_index=True, use_container_width=True)
    else:
        st.caption("No alerts: every protected rule matches its signed version.")


@st.fragment(run_every=3)
def rules_page():
    engine_banner()
    rows = get("/api/rules") or []
    s = get("/api/rules/summary") or {}
    st.caption(f"{s.get('verified', 0)} of {s.get('protected', 0)} signed rules verified on the switch")
    flt = st.radio("Filter", ["all", "ok", "altered", "shadow", "forged", "missing", "pending"], horizontal=True,
                   key="rule_filter")
    shown = [r for r in rows if flt == "all" or r.get("status") == flt]
    if not shown:
        st.info("No rules with this status.")
        return
    df = pd.DataFrame([{"status": STATUS_ICON.get(r["status"], r["status"]), "switch": r["dpid"], "table": r["table_id"],
                        "priority": r["priority"], "match": fmt_match(r.get("match")), "on switch": fmt_instr(r.get("instructions")) if r.get("present") else "(absent)",
                        "signed": fmt_instr(r.get("golden_instructions")), "cookie": r.get("cookie") or "-",
                        "verified": ts(r.get("last_verified"))} for r in shown])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.subheader("Rule details: signed by the controller vs on the switch now")
    labels = [f"t{r['table_id']} p{r['priority']}  {fmt_match(r.get('match'))}  [{r['status']}]" for r in shown]
    i = st.selectbox("Rule", range(len(shown)), format_func=lambda k: labels[k], key="rule_pick")
    r = shown[i]
    a, b = st.columns(2)
    a.markdown("**Signed by the controller**")
    a.code(f"{fmt_instr(r.get('golden_instructions')) if r.get('golden') else '(no signed rule for this slot)'}\n"
           f"cookie {r.get('golden_cookie') or '-'}")
    a.markdown(stripe(r.get("golden_cookie")), unsafe_allow_html=True)
    b.markdown("**On the switch now**")
    b.code(f"{fmt_instr(r.get('instructions')) if r.get('present') else '(rule is missing)'}\ncookie {r.get('cookie') or '-'}")
    if r.get("present"):
        b.markdown(stripe(r.get("cookie"), r.get("golden_cookie")), unsafe_allow_html=True)
    if r["status"] == "ok":
        st.success("Matches the signed rule the controller installed.")
    elif r["status"] == "pending":
        st.info("The engine is checking or repairing this slot.")
    else:
        st.error(f"{r['status'].upper()}: the switch differs from the signed policy.")
        if is_admin and st.button("Repair this rule", type="primary", key=f"rep{i}"):
            c, body = api("POST", "/api/rules/repair", json={"dpid": r["dpid"], "table_id": r["table_id"],
                                                            "priority": r["priority"], "match": r.get("match") or {}})
            (st.success if c == 202 else st.error)("Repair requested; the engine acts within about a second."
                                                   if c == 202 else f"Repair refused: {body}")
        elif not is_admin:
            st.caption("Only an admin can request a repair.")


KIND_TEXT = {"altered": "A signed rule was changed on the switch",
             "forged": "A rule the controller never installed appeared",
             "missing": "A signed rule was deleted from the switch",
             "shadow": "A new higher-priority rule hides a signed rule",
             "unattributed_change": "The table changed and changed back (tamper-and-revert)"}
REASON_TEXT = {"not_in_golden_store": "no signed rule exists for this slot", "instructions_differ": "actions differ from "
               "the signed rule", "missing_on_switch": "signed rule is absent from the switch"}


def repair_bad_rules():
    for row in [r for r in (get("/api/rules") or []) if r.get("status") not in ("ok", "pending")]:
        api("POST", "/api/rules/repair", json={"dpid": row["dpid"], "table_id": row["table_id"],
                                              "priority": row["priority"], "match": row.get("match") or {}})


@st.fragment(run_every=2)
def live_page():
    engine_banner()
    items = (get("/api/alerts?limit=100") or {}).get("items", [])
    seen = st.session_state.setdefault("seen_alerts", {a["id"] for a in items})
    new = [a for a in items if a["id"] not in seen]
    for a in reversed(new):
        st.toast(f"{a['kind'].upper()} detected \u00b7 priority {a['priority']}", icon="\u26a0\ufe0f")
        seen.add(a["id"])
    if new:
        st.session_state.last_alarm = (time.time(), new[0])
    t_alarm, last = st.session_state.get("last_alarm", (0, None))
    bad = [r for r in (get("/api/rules") or []) if r.get("status") not in ("ok", "pending")]

    # ---- alarm / all-clear banner
    if last and time.time() - t_alarm < 45:
        lat = last.get("detect_latency_ms")
        st.markdown(f'<div class="fg-card" style="border-color:#ef4444;background:#450a0a"><h4>\u26a0 TAMPERING DETECTED · '
                    f'{esc(last["kind"].upper())}</h4><p style="color:#fecaca">{esc(KIND_TEXT.get(last["kind"], last["summary"]))} · '
                    f'table {last["table_id"]}, priority {last["priority"]} · detected '
                    f'{f"in {lat} ms" if lat is not None else "by " + esc(last["detected_by"])} · action: {esc(last["action"])}</p>'
                    '</div>', unsafe_allow_html=True)
    elif not bad:
        st.markdown('<div class="fg-card" style="border-color:#10b981"><h4>\u25cf All signed rules match the switch</h4>'
                    '<p>Watching every change on the switch. Any change made outside the controller appears here '
                    'within milliseconds.</p></div>', unsafe_allow_html=True)
    st.write("")

    # ---- rules that are wrong right now
    if bad:
        st.error(f"{len(bad)} rule(s) on the switch differ from the signed policy right now")
        for r in bad:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{r['status'].upper()}** · table {r['table_id']} · priority {r['priority']} · "
                        f"`{fmt_match(r.get('match'))}` · signed: `{fmt_instr(r.get('golden_instructions'))}` · "
                        f"on switch: `{fmt_instr(r.get('instructions')) if r.get('present') else 'absent'}`")
        if is_admin and st.button("Repair all now", type="primary", key="repair_all"):
            repair_bad_rules()
            st.success("Repair requested; the engine restores the signed policy within about a second.")

    # ---- counters per kind
    by_kind = (get("/api/reports/summary") or {}).get("alerts_by_kind") or {}
    cols = st.columns(5)
    for col, k in zip(cols, KINDS):
        col.metric(k.replace("_", " ").title(), by_kind.get(k, 0))

    if not items:
        st.info("No detections yet.")
        return

    # ---- timeline
    df = pd.DataFrame([{"time": datetime.fromtimestamp(a["t"]), "kind": a["kind"],
                        "detect ms": a["detect_latency_ms"] if a["detect_latency_ms"] is not None else 0} for a in items])
    st.markdown("#### Detection timeline")
    st.scatter_chart(df, x="time", y="detect ms", color="#FF7070", height=230)

    # ---- detections
    st.markdown("#### Detections (newest first)")
    for a in items[:12]:
        icon = "\u25a0" if a["severity"] in ("high", "critical") else "\u25b2"
        with st.expander(f"{icon} {ts(a['t'])} · {a['kind']} · priority {a['priority']} · {a['action']}"
                         f"{' · acknowledged' if a['status'] == 'acknowledged' else ''}", expanded=a in new):
            d = (get(f"/api/alerts/{a['id']}") or {}).get("details") or {}
            st.markdown(f"**What happened:** {a['summary']}")
            if d.get("reasons"):
                st.markdown("**Why it was flagged:** " + "; ".join(REASON_TEXT.get(x, x) for x in d["reasons"]))
            g, o = d.get("golden") or {}, d.get("observed") or {}
            c1, c2 = st.columns(2)
            c1.markdown("**Signed by the controller**")
            c1.code(f"{fmt_instr(g.get('instructions')) if g else '(no signed rule)'}\ncookie {g.get('cookie', '-') if g else '-'}")
            c1.markdown(stripe(g.get("cookie") if g else None), unsafe_allow_html=True)
            c2.markdown("**Found on the switch**")
            c2.code(f"{fmt_instr(o.get('instructions')) if o else '(rule absent)'}\ncookie {o.get('cookie', '-') if o else '-'}")
            if o:
                c2.markdown(stripe(o.get("cookie"), g.get("cookie") if g else None), unsafe_allow_html=True)
            t = d.get("timing") or {}
            m = st.columns(4)
            m[0].metric("Detect", f"{a['detect_latency_ms']} ms" if a["detect_latency_ms"] is not None else "-")
            m[1].metric("Respond", f"{t.get('respond_latency_ms')} ms" if t.get("respond_latency_ms") is not None else "-")
            m[2].metric("Restore", f"{a['time_to_restore_ms']} ms" if a["time_to_restore_ms"] is not None else "-")
            m[3].metric("Detected by", a["detected_by"] or "-")
            if is_analyst and a["status"] != "acknowledged" and st.button("Acknowledge", key=f"ack_{a['id']}"):
                api("POST", f"/api/alerts/{a['id']}/ack")


def alerts_page():
    engine_banner()
    tab1, tab2 = st.tabs(["Alerts", "Incidents"])
    with tab1:
        k = st.selectbox("Kind", ["all"] + KINDS)
        q = "/api/alerts?limit=200" + ("" if k == "all" else f"&kind={k}")
        items = (get(q) or {}).get("items", [])
        if not items:
            st.info("No alerts.")
        else:
            st.dataframe(pd.DataFrame([{"time": ts(a["t"]), "kind": a["kind"], "severity": a["severity"],
                                        "priority": a["priority"], "action": a["action"], "status": a["status"],
                                        "ack by": a["acknowledged_by"] or "", "detect ms": a["detect_latency_ms"],
                                        "restore ms": a["time_to_restore_ms"], "incident": a["incident_id"]}
                                       for a in items]), hide_index=True, use_container_width=True)
            pick = st.selectbox("Alert", items, format_func=lambda a: f"{ts(a['t'])} {a['kind']} p{a['priority']} ({a['status']})")
            full = get(f"/api/alerts/{pick['id']}") or {}
            st.markdown(f"**What happened:** {pick['summary']}")
            d = full.get("details") or {}
            c1, c2 = st.columns(2)
            c1.markdown("**Signed (golden)**")
            c1.json(d.get("golden") or {}, expanded=False)
            c2.markdown("**Observed on the switch**")
            c2.json(d.get("observed") or d.get("actual") or {}, expanded=False)
            if is_analyst and pick["status"] != "acknowledged" and st.button("Acknowledge", key="ack"):
                api("POST", f"/api/alerts/{pick['id']}/ack")
                st.rerun()
    with tab2:
        inc = (get("/api/incidents?limit=100") or {}).get("items", [])
        if not inc:
            st.info("No incidents.")
            return
        st.dataframe(pd.DataFrame(inc), hide_index=True, use_container_width=True)
        i = st.selectbox("Incident", inc, format_func=lambda x: f"#{x['id']} {x['title']} ({x['status']})")
        det = get(f"/api/incidents/{i['id']}") or {}
        for n in det.get("notes", []):
            st.markdown(f"- *{ts(n['t'])} {n['username']}:* {n['text']}")
        if is_analyst:
            c = st.columns(3)
            new_status = c[0].selectbox("Status", ["open", "acknowledged", "closed"],
                                        index=["open", "acknowledged", "closed"].index(i["status"]))
            assignee = c[1].text_input("Assignee", value=i.get("assignee") or "")
            if c[2].button("Save"):
                api("PATCH", f"/api/incidents/{i['id']}", json={"status": new_status, "assignee": assignee})
                st.rerun()
            note = st.text_area("Add note")
            if st.button("Add note") and note.strip():
                api("POST", f"/api/incidents/{i['id']}/notes", json={"text": note.strip()})
                st.rerun()


@st.fragment(run_every=5)
def topology_page():
    eng, sws = engine_banner()
    hosts = ((eng.get("status") or {}).get("hosts") or {})
    dot = ['digraph G { rankdir=TB; node [shape=box, style="rounded,filled", fontname="Helvetica"];',
           'engine [label="FlowGuard engine\\n(Ryu controller)", fillcolor="#dbeafe"];']
    for s in sws:
        col = "#bbf7d0" if s.get("connected") and s.get("monitor_up") else "#fecaca"
        dot.append(f'"{s["dpid"]}" [label="Switch {s.get("name") or "s1"}\\n{s["dpid"]}", fillcolor="{col}"];')
        dot.append(f'engine -> "{s["dpid"]}" [label="OpenFlow 1.3 · monitored", dir=both];')
        for mac, port in sorted((hosts.get(s["dpid"]) or {}).items(), key=lambda x: x[1]):
            dot.append(f'"{mac}" [label="Host on port {port}\\n{mac}", fillcolor="#f1f5f9"];')
            dot.append(f'"{s["dpid"]}" -> "{mac}" [dir=none];')
    dot.append("}")
    st.graphviz_chart("\n".join(dot), use_container_width=True)
    st.caption("Hosts are the MAC/port pairs the learning switch (table 1) has seen. Inter-switch links are not "
               "discovered (no LLDP).")


def policy_page():
    pol = get("/api/policies")
    st.info("The policy below is stored and versioned by the core but **not enforced yet** (Phase 5 risk engine). "
            "The engine enforces its policy file; protected rules are signed and installed only by the controller.")
    st.json(pol or {}, expanded=True)


def reports_page():
    rep = get("/api/reports/summary") or {}
    c = st.columns(3)
    c[0].metric("Alerts", rep.get("alerts_total", 0))
    c[1].metric("Open incidents", rep.get("open_incidents", 0))
    dl = rep.get("detect_latency_ms") or {}
    c[2].metric("Median detect", f"{dl.get('median')} ms" if dl else "-")
    if rep.get("alerts_by_kind"):
        st.bar_chart(pd.Series(rep["alerts_by_kind"], name="alerts"))
    st.json(rep, expanded=False)
    if is_analyst:
        r = requests.get(CORE + "/api/reports/alerts.csv", headers={"Authorization": f"Bearer {st.session_state.token}"},
                         timeout=6)
        if r.status_code == 200:
            st.download_button("Download alerts CSV", r.content, "flowguard-alerts.csv", "text/csv")


def audit_page():
    if not is_analyst:
        st.warning("Analyst or admin role required.")
        return
    if is_admin:
        v = get("/api/audit/verify") or {}
        (st.success if v.get("ok") else st.error)(
            f"Hash chain {'intact' if v.get('ok') else 'BROKEN at id ' + str(v.get('first_bad_id'))} "
            f"({v.get('rows_checked', 0)} rows checked)")
    items = (get("/api/audit?limit=300") or {}).get("items", [])
    st.dataframe(pd.DataFrame([{"time": ts(e["t"]), "user": e["username"], "role": e["role"], "action": e["action"],
                                "target": e["target"], "result": e["result"], "hash": (e["hash"] or "")[:16]}
                               for e in items]), hide_index=True, use_container_width=True)


def engine_page():
    eng, _ = engine_banner()
    st.json(eng, expanded=False)
    st.subheader("Quarantined ports")
    quarantined = (get("/api/quarantine") or {}).get("items", [])
    if not quarantined:
        st.caption("No port is quarantined. A port is cut only when the policy action is quarantine_port, dry run is off, and the finding names a port.")
    for item in quarantined:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"Switch `{item['dpid']}` \u00b7 port **{item['port']}** \u00b7 since {ts(item['t'])}")
        if is_admin and c2.button("Release", key=f"rel_{item['dpid']}_{item['port']}"):
            code, body = api("POST", "/api/quarantine/release", json={"dpid": item["dpid"], "port": item["port"]})
            (st.success if code == 202 else st.error)("Release requested; the engine lifts it within a second." if code == 202 else f"Refused: {body}")
    st.subheader("Recent engine events")
    ev = get("/api/events?limit=50") or []
    if ev:
        st.dataframe(pd.DataFrame([{"time": ts(e["t"]), "kind": e["kind"], "switch": e["dpid"],
                                    "data": json.dumps(e["data"])[:160]} for e in ev]), hide_index=True, use_container_width=True)
    if is_admin:
        st.subheader("Key rotation")
        st.caption("Starts a new key epoch: every protected rule is re-signed; no alerts are expected.")
        if st.button("Rotate HMAC key"):
            c, b = api("POST", "/api/engine/rotate-key")
            (st.success if c == 202 else st.error)(b.get("note") if isinstance(b, dict) else b)


def users_page():
    if not is_admin:
        st.warning("Admin role required.")
        return
    us = get("/api/users") or []
    st.dataframe(pd.DataFrame(us), hide_index=True, use_container_width=True)
    with st.form("newuser"):
        st.subheader("Add user")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        r = st.selectbox("Role", ["viewer", "analyst", "admin"])
        if st.form_submit_button("Create"):
            c, b = api("POST", "/api/users", json={"username": u, "password": p, "role": r})
            (st.success if c == 201 else st.error)("User created." if c == 201 else str(b))


def planned_page():
    probes, ml = get("/api/probes") or {}, get("/api/ml/scores") or {}
    st.info("**L2 canary probes** and **L3 anomaly scores** are produced inside the engine. " + (probes.get("note") or ""))
    a, b = st.columns(2)
    a.markdown("#### L2 probe results")
    if probes.get("items"):
        a.dataframe(pd.DataFrame([{"time": ts(i["t"]), "switch": i["dpid"], "priority": i["data"].get("priority"), "expect": i["data"].get("expect"),
                                   "status": i["data"].get("status"), "why": i["data"].get("reason")} for i in probes["items"]]), hide_index=True, use_container_width=True)
    else:
        a.caption("No probe results yet.")
    b.markdown("#### L3 anomaly scores")
    if ml.get("items"):
        b.dataframe(pd.DataFrame([{"time": ts(i["t"]), "switch": i["dpid"], "score": i["score"], "why": "; ".join(i["data"].get("reasons") or [])} for i in ml["items"]]),
                    hide_index=True, use_container_width=True)
    else:
        b.caption("A score appears for each detected rule change.")


# ---- Demo Lab: SIMULATED four-switch network (in-memory; nothing is sent to any switch or the engine) -----------------
DEMO_SW = {"s1": "core", "s2": "edge-west", "s3": "edge-mid", "s4": "edge-east"}
DEMO_KINDS = [("altered", "Change a rule"), ("forged", "Add an unknown rule"), ("missing", "Delete a rule"),
              ("shadow", "Hide a rule"), ("unattributed_change", "Change and revert")]


def _cookie(seed):
    return hashlib.sha1(seed.encode()).hexdigest()[:16]


def demo_page():
    st.info("**Simulated lab.** This page edits an in-memory model of four switches. It sends nothing to any switch or to "
            "the engine, and FlowGuard runs no attacks. It shows what FlowGuard would report if rules were changed.")
    d = st.session_state.setdefault("demo", {"bad": {}, "events": []})
    sw = st.radio("Switch to tamper with", list(DEMO_SW), horizontal=True, format_func=lambda k: f"{k.upper()} \u00b7 {DEMO_SW[k]}")
    cols = st.columns(5)
    for c, (k, label) in zip(cols, DEMO_KINDS):
        if c.button(label, key=f"demo_{k}", use_container_width=True):
            signed = _cookie(f"{sw}-r1")
            found = None if k == "missing" else (_cookie(f"{sw}-x") if k in ("forged", "shadow") else signed[:12] + _cookie(signed)[:4])
            d["bad"][sw] = k
            d["events"].insert(0, {"t": time.time(), "sw": sw, "kind": k, "ms": random.randint(6, 35), "restore": None,
                                   "signed": None if k in ("forged", "shadow") else signed, "found": found})
    a, b, _ = st.columns([1, 1, 4])
    if a.button("Repair now", type="primary"):
        d["bad"].clear()
        for e in d["events"]:
            e["restore"] = e["restore"] or random.randint(300, 800)
    if b.button("Reset"):
        st.session_state.pop("demo", None)
        st.rerun()

    dot = ['graph G { rankdir=TB; node [shape=box, style="filled", fontname="Helvetica", fontcolor="#1B1B19"];',
           'eng [label="FlowGuard engine", fillcolor="#182436", fontcolor="#ffffff"];']
    for k, n in DEMO_SW.items():
        bad = k in d["bad"]
        dot.append(f'{k} [label="{k.upper()} {n}\\n{"TAMPERED" if bad else "verified"}", fillcolor="{"#FF9A9A" if bad else "#8fe0a8"}"];')
        dot.append(f'eng -- {k} [style=dashed];')
    dot += ["s1 -- s2;", "s1 -- s3;", "s1 -- s4;", "s2 -- s3;"]
    for h, k in zip(["h1", "h2", "h3", "h4", "h5", "h6"], ["s2", "s2", "s3", "s3", "s4", "s4"]):
        dot.append(f'{h} [shape=ellipse, fillcolor="#ECE8DC"]; {k} -- {h};')
    dot.append("}")
    st.graphviz_chart("\n".join(dot), use_container_width=True)

    st.markdown("#### Patch panel by switch")
    for k, n in DEMO_SW.items():
        st.markdown(f"**{k.upper()} \u00b7 {n}**" + port_strip(["altered" if k in d["bad"] else "ok"] + ["ok"] * 3), unsafe_allow_html=True)

    st.markdown("#### What FlowGuard caught")
    if not d["events"]:
        st.caption("Nothing yet. Pick a switch and run a scenario above.")
    for e in d["events"]:
        st.markdown(f'<div class="fg-card" style="margin-bottom:8px"><h4>{e["kind"].replace("_", " ").upper()} \u00b7 {e["sw"]}</h4>'
                    f'<p>{ts(e["t"])} \u00b7 detected in <b>{e["ms"]} ms</b> \u00b7 '
                    f'{"repair pending" if e["restore"] is None else "restored in " + str(e["restore"]) + " ms"}</p><br>'
                    f'signed {stripe(e["signed"])} &nbsp; found {stripe(e["found"], e["signed"]) if e["found"] else "(rule absent)"}'
                    '</div>', unsafe_allow_html=True)


PAGES = dict(zip(NAV, [overview, rules_page, live_page, demo_page, alerts_page, topology_page, policy_page, reports_page,
                       audit_page, engine_page, users_page, planned_page]))
SHOWS_BANNER = {overview, rules_page, live_page, demo_page, alerts_page, topology_page, engine_page}
if PAGES[page] not in SHOWS_BANNER:
    engine_banner()
PAGES[page]()
