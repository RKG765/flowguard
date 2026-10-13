# FlowGuard architecture (as built)

This file describes what EXISTS. Every component carries a tag: `implemented` (verified by a command recorded in `docs/graphs/status.json`), `partial`, or `planned`. After Phase 0 only the lab and tooling exist; the diagrams below show the target structure with unbuilt parts marked in the tag table.

## Component tags
<!-- AUTO:component_tags -->
| Component | Tag | Phase it lands in |
|---|---|---|
| Living docs + status tooling (update_docs.py) | `implemented` | 0 |
| Environment doctor + flowguard CLI (doctor only) | `implemented` | 0 |
| scripts/setup_ubuntu.sh | `partial` | 0 |
| Mininet lab topology (4 hosts, 1 or 2 switches, explicit dpids) | `implemented` | 0 |
| Phase 0 spike harness (make spike) | `implemented` | 0 |
| Canonical form + HMAC cookie (dpid, epoch bound) | `planned` | 1 |
| Golden store + install_signed_rule | `planned` | 1 |
| L1 verifier + NXST monitor session | `planned` | 1 |
| Responder (restore, rate limit) | `planned` | 1 |
| ZeroMQ event channel + alert spool | `planned` | 1 |
| Core service (FastAPI, SQLite, WebSocket) | `planned` | 2 |
| Auth, roles, audit log | `planned` | 2 |
| Privileged helper (allowlist) | `planned` | 4 |
| Attacks A1-A7 (A7 SIMULATED) | `planned` | 4 |
| Design system + app shell | `planned` | 3 |
| Dashboard pages + Attack Lab | `planned` | 4 |
| L2 data-plane prober | `planned` | 5 |
| L3 ML scorer worker | `planned` | 5 |
| Risk engine + policy | `planned` | 5 |
| Reports (PDF/CSV) | `planned` | 6 |
| flowguard CLI (start, stop, status, export) and make targets | `planned` | 7 |
<!-- /AUTO:component_tags -->

## System context (target)
```mermaid
flowchart LR
  Admin[Network admin browser] -->|http localhost:8787| Core
  subgraph Host[Lab host: WSL2 or native Ubuntu]
    Core[Core service FastAPI]
    Engine[Ryu engine: signer verifier prober responder]
    Helper[Privileged helper root allowlist]
    ML[ML worker]
    OVS[Open vSwitch + Mininet]
  end
  Engine <-->|OpenFlow 1.3 tcp 6653| OVS
  Engine -->|ZeroMQ events| Core
  Core --> ML
  Core -->|unix socket allowlisted calls| Helper
  Helper -->|starts lab, runs attacks| OVS
  OVS -->|passive port: OF1.0 NXST monitor| Engine
```

## Event data flow (L1, as designed from the Phase 0 spike)
```mermaid
sequenceDiagram
  participant A as Attacker (ovs-ofctl)
  participant S as OVS switch
  participant M as Monitor session (OF1.0 NXST)
  participant E as Engine verifier (Ryu, OF1.3)
  participant C as Core service
  A->>S: mod-flows / add-flow / del-flows
  S-->>M: flow update event (table, cookie)
  M->>E: trigger for critical table
  E->>S: OFPFlowStatsRequest(table_id)
  S-->>E: current rules
  E->>E: compare with signed golden rules (HMAC cookie)
  E->>S: restore golden rule (rate limited)
  E-->>C: alert + timings (spool first, then ZeroMQ)
```

## Deployment: WSL2 vs native Ubuntu
```mermaid
flowchart TB
  subgraph W[WSL2 Ubuntu 22.04 on Windows]
    W1[systemd available when enabled in wsl.conf]
    W2[OVS kernel module loads on kernel 6.6.87.2 verified; netdev fallback verified]
    W3[Dashboard on 127.0.0.1:8787 reached from Windows browser via localhost forwarding]
  end
  subgraph N[Native Ubuntu 22.04 laptop]
    N1[systemd units]
    N2[Kernel datapath expected; not yet verified]
    N3[Dashboard on 127.0.0.1:8787]
  end
```

## Trust boundaries
```mermaid
flowchart LR
  subgraph Trusted
    K[HMAC key file 0600]
    G[Golden store]
    Eng[Engine]
    Cor[Core]
  end
  subgraph Untrusted
    Sw[OVS switch tables and stats replies]
    Adm[Local admin and processes on the switch OS]
  end
  Sw -.->|may lie or be modified| Eng
  Adm -.->|ovs-ofctl| Sw
```
In the lab the trusted and untrusted boxes share one host (see `docs/threat_model.md`).

## Data model (ER, target; migrations arrive in Phase 2)
```mermaid
erDiagram
  SWITCH ||--o{ RULE : has
  RULE ||--o{ ALERT : triggers
  ALERT }o--|| INCIDENT : grouped_in
  ALERT ||--o{ RESPONSE : answered_by
  USER ||--o{ AUDIT_EVENT : performs
  SESSION ||--o{ ALERT : records
```

## Generated graphs
The component graph and phase graph are generated from `docs/graphs/status.json` by `make docs`:
<!-- AUTO:components_graph -->
```mermaid
flowchart TB
  docs_tooling["Living docs + status tooling (update_docs.py)"]:::implemented
  doctor["Environment doctor + flowguard CLI (doctor only)"]:::implemented
  setup_script["scripts/setup_ubuntu.sh"]:::partial
  lab_topology["Mininet lab topology (4 hosts, 1 or 2 switches, explicit dpids)"]:::implemented
  spike_harness["Phase 0 spike harness (make spike)"]:::implemented
  engine_crypto["Canonical form + HMAC cookie (dpid, epoch bound)"]:::planned
  engine_store["Golden store + install_signed_rule"]:::planned
  engine_verifier["L1 verifier + NXST monitor session"]:::planned
  engine_responder["Responder (restore, rate limit)"]:::planned
  event_channel["ZeroMQ event channel + alert spool"]:::planned
  core_service["Core service (FastAPI, SQLite, WebSocket)"]:::planned
  core_auth["Auth, roles, audit log"]:::planned
  helper["Privileged helper (allowlist)"]:::planned
  attacks["Attacks A1-A7 (A7 SIMULATED)"]:::planned
  web_design_system["Design system + app shell"]:::planned
  web_pages["Dashboard pages + Attack Lab"]:::planned
  engine_prober["L2 data-plane prober"]:::planned
  ml_worker["L3 ML scorer worker"]:::planned
  risk_engine["Risk engine + policy"]:::planned
  reports["Reports (PDF/CSV)"]:::planned
  packaging["flowguard CLI (start, stop, status, export) and make targets"]:::planned
  lab_topology --> engine_verifier
  engine_crypto --> engine_store
  engine_store --> engine_verifier
  engine_verifier --> engine_responder
  engine_verifier --> event_channel
  engine_prober --> risk_engine
  ml_worker --> risk_engine
  event_channel --> core_service
  risk_engine --> core_service
  core_auth --> core_service
  core_service --> web_pages
  web_design_system --> web_pages
  core_service --> helper
  helper --> attacks
  core_service --> reports
  classDef done fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;
  classDef in_progress fill:#b7791f,stroke:#5c3b0d,color:#ffffff;
  classDef not_started fill:#4a5568,stroke:#1a202c,color:#ffffff;
  classDef blocked fill:#c53030,stroke:#63171b,color:#ffffff;
  classDef implemented fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;
  classDef partial fill:#b7791f,stroke:#5c3b0d,color:#ffffff;
  classDef planned fill:#4a5568,stroke:#1a202c,color:#ffffff;
```
<!-- /AUTO:components_graph -->
