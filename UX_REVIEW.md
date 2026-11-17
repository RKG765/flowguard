# UX and design review (network administrator persona)

**This is an AI-simulated review. No human has tested this product.** Real network operators and a few students should try
it before anyone relies on these conclusions. The reviewer was Impeccable's finish reviewer (a fresh AI context, read-only),
working from screenshots and code, over three rounds on 2026-11-17: a first round that refused to judge because my captures
were invalid (full-page shots cut the sticky rail, no mobile capture, only empty states), a full review, and a scoring pass.

## What was looked at
Live captures of the website (dark and light, 1440x900 and 390x844) and of the Streamlit console, taken against a real
Open vSwitch lab with one forged rule and one altered rule left unrepaired; files in `.impeccable/review/`. The design
direction is "Patch Panel" (`PRODUCT.md`, `.impeccable/surfaces/web-src-pages-overview-tsx.md`).

## What the review found and what was done
| Finding | Result |
|---|---|
| Dark theme drifted to the blue-black default; the blue rail did not read as committed | **fixed** (neutral warm grey ground) |
| Port strip small, text glyphs, `ok` colour-only | **fixed**: numbered tiles that share the full width, drawn icons incl. a check for ok, tag stripe per tile |
| "Changed row stays lit until acknowledged" was not implemented | **fixed**: unacknowledged alerts keep their rule lit after repair; Acknowledge button on the rule |
| Remediation mode missing from the top bar | **fixed** (Auto-repair / Alert only) |
| Event feed marked tampering events INFO; port count disagreed with the KPI | **fixed** |
| Nested cards (defense layers, Demo Lab items) | **fixed** |
| Tag stripe of an unsigned rule drew eight identical blue bands | **fixed**: shows "no tag" |
| No mobile layout: rail did not collapse | **fixed**: compact scrolling nav, status as a dot, tables and the topology scroll sideways |
| Stock toasts that ignored the live theme | **fixed** |
| Console: clipped titles, Deploy button and rainbow line, left-border header, misleading green delta, glyph ports | **fixed** (last items in the final pass; checked by build and test, not by a further screenshot round) |
| PRODUCT.md said L2/L3 were not built and nothing was simulated | **fixed** |

## Still open
- **Mobile tables:** the Rules table and the Demo Lab topology scroll sideways but give no visual cue that they do.
- **Not captured:** a toast, the lit state after a repair (a still image cannot show a pulse), the final port tiles at 1440 on the
  live Overview (the Demo Lab shows them), the console at the very end (compiled and exercised, not re-screenshotted).
- **Console:** fonts load from Google Fonts with a Segoe UI fallback, so offline it looks more like default Streamlit; it has no automated UI test.
- **Leftovers:** `glass-*` token names and the `GlassCard` component name remain from the first design (kept because the contrast test reads them).
- No QUALITY BAR image set was used (code-led build), so the reviewer judged against the design contract only.
- Tablet widths, screen readers beyond the axe checks, and real users: not tested.

## For the presentation
The Overview, Rules (signed vs found with stripes), Demo Lab and Policy pages are the strongest; start there.
