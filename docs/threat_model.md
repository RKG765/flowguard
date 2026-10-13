# FlowGuard threat model

Status: written in Phase 0, before the detector exists. Nothing here claims detection works; the coverage map is filled with evidence in Phases 9-10.

## What is protected
The integrity of OpenFlow flow rules (match, priority, instructions) in the *critical tables* (default: table 0, the security/ACL table) of Open vSwitch switches controlled by a Ryu controller, and the forwarding behavior those rules should produce.

## In scope (FlowGuard aims to detect these)
| ID | Threat | Layer expected to catch it |
|---|---|---|
| T1 | A rogue admin or local process runs `ovs-ofctl add-flow` and installs a rule the controller never signed (forged) | L1 |
| T2 | The same actor `mod-flows` an existing signed rule (altered) | L1 |
| T3 | The same actor `del-flows` a signed rule (missing) | L1 |
| T4 | A higher-priority rule shadows a signed rule | L1 |
| T5 | Malware on the switch OS tampers and quickly reverts between observations | L1 (event-driven monitor; Phase 0 evidence: `docs/spike_findings.md`) |
| T6 | A switch returns falsified flow-stats replies (rules hidden or invented) | L2 (data-plane canaries); this is SIMULATED in the lab (attack A7) |
| T7 | A malicious but validly signed rule is pushed through the controller (insider, compromised controller app) | L3 (ML scoring, out of band); L1 cannot catch it by design |

## Trusted components (stated openly as limitations)
- The controller host, the FlowGuard services, and the HMAC key. If any of them is compromised, L1 is bypassed.
- **Lab limitation:** in the lab the controller, the HMAC key, the OVS switch and the attacker's shell all share one host. A root attacker on that host can read the key file (and the golden store) and forge valid cookies. The lab therefore demonstrates detection of *non-key-holding* attackers only; it does not demonstrate resistance to a root attacker on the controller host. A real deployment must separate the controller and key from the switches.
- Open vSwitch itself and the OpenFlow channel between switch and controller (assumed to be local TCP in the lab; no TLS is claimed).

## Out of scope
- Stolen controller key; physical attacks; data-plane DoS; attacks on Mininet hosts' applications.
- Anything outside the lab network. The Attack Lab only targets lab switches the privileged helper created itself.

## Known blind spots (design-level, to be measured not hidden)
- Tamper-and-revert: the monitor event stream still reports the change, but by the time the confirming stats request runs the table may already match the golden rules. The verifier must therefore also raise an `unattributed_change` alert for any critical-table event that the engine's own FlowMods do not explain (design, Phase 1; ADR-004). If the monitor session is silently dropped, only the slow reconciliation poll remains (default 5 s) and a revert faster than that is missed.
- Rules in non-critical tables (default: table 1, learning switch) are not verified.
- L2 only probes critical rules at a low rate, so it samples behavior rather than proving it.
- L3 is probabilistic and can be evaded by slow drift (tested in Phase 10).

## Abuse cases for the product itself (reviewed in Phase 10)
Alert flooding to hide a real attack; copying a valid cookie onto a different rule/table/switch/priority; replaying old signed rules after key rotation; exploiting the grace window; attacking the golden store or event channel; abusing the privileged helper through the web layer; privilege escalation viewer -> admin; leaking key or tags through UI/API/logs/exports.
