# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Network and SOC operators watching an SDN lab (Ryu controller + Open vSwitch) for unauthorized flow-rule changes, usually on a large monitor in a dim room, reacting to alerts within seconds. Secondary audience: the project owner presenting the system to a student panel, so the main screens must also be understood in seconds on a projector. Roles in the product: admin, analyst, viewer.

## Product Purpose
FlowGuard detects forged, altered, shadowing and missing flow rules on OpenFlow switches by checking an HMAC tag carried in each rule's cookie, and restores the signed rule. The website (React dashboard in web/) and the console (Streamlit, ui/streamlit_app.py) are two front ends over the same core API. Success: an operator sees within one glance whether every signed rule matches the switch, and on an alert sees signed-vs-found and can acknowledge or repair.

## Positioning
Rule integrity is proven cryptographically per rule, then checked live on the switch, rather than inferred from traffic statistics.

## Operating Context
Local lab on WSL2 or Ubuntu, core API at 127.0.0.1:8787, dashboard 5173, Streamlit 8501. Live data comes from the engine; only the Demo Lab pages are simulated and are labelled Simulated. Pages: Overview, Topology, Rules, Alerts and Incidents, Live Detection, Demo Lab, Probes (L2), ML (L3), Policy, Reports, Audit, Settings.

## Capabilities and Constraints
- Detection kinds: altered, forged, missing, shadow, unattributed change (tamper-and-revert). Statuses: ok, altered, forged, missing, shadow, pending.
- Observation only: no attack execution anywhere in the product (ADR-019). Do not add attack buttons or attack wording.
- L2 canary probes, the L3 anomaly scorer (a statistical baseline, not a neural network) and the risk engine (policy, port quarantine) are built. A layer is shown Active only when the API reports results for it. The Demo Lab pages are simulations and must say so.
- Both themes (light and dark) exist in the web app today and must keep WCAG AA contrast; status is never colour alone (icon plus label). Reduced motion respected.
- Python tooling is managed with uv.

## Evidence on Hand
Live engine and alert data through the core API, tests in web/ (contrast, axe, Playwright), screenshots in docs/img. No customers, benchmarks or testimonials exist; do not invent any.

## Product Principles
- Truth over decoration: every number comes from the engine, empty states say so.
- Integrity states must be readable at a glance from across a room.
- Show signed vs found side by side; the diff is the product.
- Calm when healthy, unmistakable when not.
