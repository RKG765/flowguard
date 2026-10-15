"""FlowGuard operator console (Streamlit). A second front end over the same core API the React dashboard uses.

Run (with `sudo make demo` or `sudo make present` already running):  make ui   ->  http://127.0.0.1:8501
Local-only console: it listens on 127.0.0.1 and signs in to the local core automatically (FG_USER / FG_PASSWORD,
default: the demo account `make present` creates). Read-only monitoring plus the operator actions the API allows (acknowledge, incidents, admin repair, users, key
rotation). Like the main dashboard it has no attack execution (ADR-019). L2 probes and L3 ML are Phase 5 placeholders.
"""
import json
import os
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

CORE = os.environ.get("FG_CORE_URL", "http://127.0.0.1:8787")
KINDS = ["altered", "forged", "missing", "shadow", "unattributed_change"]
STATUS_ICON = {"ok": "🟢 verified", "altered": "🟠 altered", "forged": "🔴 forged", "missing": "🔴 missing",
               "shadow": "🟠 shadow", "pending": "⏳ pending"}

st.set_page_config(page_title="FlowGuard", page_icon="🛡️", layout="wide")


# ---- API -----------------------------------------------------------------------------------------------------------
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


# ---- look ----------------------------------------------------------------------------------------------------------
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  [data-testid="stSidebar"] {background: linear-gradient(180deg, #0f172a 0%, #111827 100%); border-right: 1px solid #1f2937;}
  [data-testid="stSidebar"] label p {font-size: 0.98rem;}
  [data-testid="stMetric"] {background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 14px 18px;}
  [data-testid="stMetricLabel"] p {color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; letter-spacing: .04em;}
  [data-testid="stMetricValue"] {font-size: 2.1rem;}
  .fg-hero {display:flex; align-items:center; justify-content:space-between; gap:16px; padding:18px 22px;
            border-radius:16px; background: linear-gradient(120deg, #1e3a8a 0%, #0f766e 100%); margin-bottom: 18px;}
  .fg-hero h1 {font-size: 1.7rem; margin: 0; color: #f8fafc;}
  .fg-hero p {margin: 2px 0 0 0; color: #dbeafe; font-size: .95rem;}
  .fg-pill {padding: 6px 14px; border-radius: 999px; font-weight: 600; font-size: .9rem; white-space: nowrap;}
  .fg-ok {background:#064e3b; color:#a7f3d0; border:1px solid #10b981;}
  .fg-warn {background:#78350f; color:#fde68a; border:1px solid #f59e0b;}
  .fg-bad {background:#7f1d1d; color:#fecaca; border:1px solid #ef4444;}
  .fg-card {background:#111827; border:1px solid #1f2937; border-radius:14px; padding:16px 18px; height:100%;}
  .fg-card h4 {margin:0 0 6px 0; font-size:1.02rem;}
  .fg-card p {margin:0; color:#94a3b8; font-size:.9rem;}
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
        st.markdown("## 🛡️ FlowGuard")
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
NAV = ["📊 Overview", "🛡️ Rules", "⚡ Live Detection", "🚨 Alerts & Incidents", "🕸️ Topology", "📜 Policy",
       "📈 Reports", "🔏 Audit log", "⚙️ Engine", "👥 Users", "🧪 L2 Probes / L3 ML (planned)"]
with st.sidebar:
    st.markdown("## 🛡️ FlowGuard")
    st.caption("SDN flow-rule integrity · operator console")
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
    st.markdown(f'<div class="fg-hero"><div><h1>{page.split(" ", 1)[1]}</h1><p>FlowGuard · signed flow rules, '
                f'verified live on the switch</p></div>{pill}</div>', unsafe_allow_html=True)
    return eng, sws


# ---- pages ---------------------------------------------------------------------------------------------------------
@st.fragment(run_every=3)
def overview():
    eng, sws = engine_banner()
    s = get("/api/rules/summary") or {}
    rep = get("/api/reports/summary") or {}
    c = st.columns(5)
    c[0].metric("Protected rules", s.get("protected", 0))
    c[1].metric("Verified", f"{s.get('verified', 0)}", f"{s.get('verified_percent', 0)}%")
    c[2].metric("Not OK now", sum((s.get("by_status") or {}).get(k, 0) for k in ("altered", "forged", "missing", "shadow")))
    c[3].metric("Alerts (total)", rep.get("alerts_total", 0))
    c[4].metric("Open incidents", rep.get("open_incidents", 0))
    st.subheader("Detection layers")
    l = st.columns(3)
    for col, (name, text, cls) in zip(l, [
            ("L1 · Signed-rule verification", "HMAC-signed rules checked on every switch change", "fg-ok"),
            ("L2 · Data-plane probes", "Planned for Phase 5", "fg-warn"),
            ("L3 · ML scoring", "Planned for Phase 5", "fg-warn")]):
        status = "active" if cls == "fg-ok" else "planned"
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
    b.markdown("**On the switch now**")
    b.code(f"{fmt_instr(r.get('instructions')) if r.get('present') else '(rule is missing)'}\ncookie {r.get('cookie') or '-'}")
    if r["status"] == "ok":
        st.success("Matches the signed rule the controller installed.")
    elif r["status"] == "pending":
        st.info("The engine is checking or repairing this slot.")
    else:
        st.error(f"{r['status'].upper()}: the switch differs from the signed policy.")
        if is_admin and st.button("🔧 Repair this rule", type="primary", key=f"rep{i}"):
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
        st.toast(f"🚨 {a['kind'].upper()} detected · priority {a['priority']}", icon="🚨")
        seen.add(a["id"])
    if new:
        st.session_state.last_alarm = (time.time(), new[0])
    t_alarm, last = st.session_state.get("last_alarm", (0, None))
    bad = [r for r in (get("/api/rules") or []) if r.get("status") not in ("ok", "pending")]

    # ---- alarm / all-clear banner
    if last and time.time() - t_alarm < 45:
        lat = last.get("detect_latency_ms")
        st.markdown(f'<div class="fg-card" style="border-color:#ef4444;background:#450a0a"><h4>🚨 TAMPERING DETECTED · '
                    f'{last["kind"].upper()}</h4><p style="color:#fecaca">{KIND_TEXT.get(last["kind"], last["summary"])} · '
                    f'table {last["table_id"]}, priority {last["priority"]} · detected '
                    f'{f"in {lat} ms" if lat is not None else "by " + str(last["detected_by"])} · action: {last["action"]}</p>'
                    '</div>', unsafe_allow_html=True)
    elif not bad:
        st.markdown('<div class="fg-card" style="border-color:#10b981"><h4>✅ All signed rules match the switch</h4>'
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
        if is_admin and st.button("🔧 Repair all now", type="primary", key="repair_all"):
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
    st.scatter_chart(df, x="time", y="detect ms", color="kind", height=230)

    # ---- detections
    st.markdown("#### Detections (newest first)")
    for a in items[:12]:
        icon = "🔴" if a["severity"] in ("high", "critical") else "🟠"
        with st.expander(f"{icon} {ts(a['t'])} · {a['kind']} · priority {a['priority']} · {a['action']}"
                         f"{' · ✔ acknowledged' if a['status'] == 'acknowledged' else ''}", expanded=a in new):
            d = (get(f"/api/alerts/{a['id']}") or {}).get("details") or {}
            st.markdown(f"**What happened:** {a['summary']}")
            if d.get("reasons"):
                st.markdown("**Why it was flagged:** " + "; ".join(REASON_TEXT.get(x, x) for x in d["reasons"]))
            g, o = d.get("golden") or {}, d.get("observed") or {}
            c1, c2 = st.columns(2)
            c1.markdown("**Signed by the controller**")
            c1.code(f"{fmt_instr(g.get('instructions')) if g else '(no signed rule)'}\ncookie {g.get('cookie', '-') if g else '-'}")
            c2.markdown("**Found on the switch**")
            c2.code(f"{fmt_instr(o.get('instructions')) if o else '(rule absent)'}\ncookie {o.get('cookie', '-') if o else '-'}")
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
            st.download_button("⬇️ Download alerts CSV", r.content, "flowguard-alerts.csv", "text/csv")


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
    st.info("**L2 data-plane probes** and **L3 ML scoring** arrive in Phase 5. The API already exposes the "
            "endpoints; they return no data until then.")
    st.json({"probes": get("/api/probes"), "ml": get("/api/ml/scores")}, expanded=False)


PAGES = dict(zip(NAV, [overview, rules_page, live_page, alerts_page, topology_page, policy_page, reports_page,
                       audit_page, engine_page, users_page, planned_page]))
SHOWS_BANNER = {overview, rules_page, live_page, alerts_page, topology_page, engine_page}
if PAGES[page] not in SHOWS_BANNER:
    engine_banner()
PAGES[page]()
