#!/usr/bin/env python3
"""Regenerate the machine-derived parts of the docs from docs/graphs/status.json.

Writes:
  * docs/graphs/progress.mmd and docs/graphs/components_status.mmd (whole files)
  * the blocks between <!-- AUTO:name --> and <!-- /AUTO:name --> markers in STATUS.md,
    ARCHITECTURE.md and README.md
Also enforces the documentation rules (see CLAUDE.md):
  * a component or phase marked implemented/done must record verified_by and verified_on
  * every metric must cite a source file that exists

Usage: update_docs.py [--check]   (--check changes nothing and exits 1 if anything is stale or invalid)
Standard library only. Rendering .mmd to .svg is best effort and only when mermaid-cli (mmdc) exists.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parent.parent
STATUS_JSON = REPO / "docs" / "graphs" / "status.json"
GRAPH_DIR = REPO / "docs" / "graphs"
MARKER_FILES = [REPO / "STATUS.md", REPO / "ARCHITECTURE.md", REPO / "README.md"]

PHASE_DONE, PHASE_PROGRESS, PHASE_TODO, PHASE_BLOCKED = "done", "in_progress", "not_started", "blocked"
PHASE_STATES = {PHASE_DONE, PHASE_PROGRESS, PHASE_TODO, PHASE_BLOCKED}
COMP_STATES = {"implemented", "partial", "planned"}

CLASS_DEFS = (
    "  classDef done fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;\n"
    "  classDef in_progress fill:#b7791f,stroke:#5c3b0d,color:#ffffff;\n"
    "  classDef not_started fill:#4a5568,stroke:#1a202c,color:#ffffff;\n"
    "  classDef blocked fill:#c53030,stroke:#63171b,color:#ffffff;\n"
    "  classDef implemented fill:#1f7a4d,stroke:#0b3d24,color:#ffffff;\n"
    "  classDef partial fill:#b7791f,stroke:#5c3b0d,color:#ffffff;\n"
    "  classDef planned fill:#4a5568,stroke:#1a202c,color:#ffffff;\n"
)


def load() -> Dict:
    return json.loads(STATUS_JSON.read_text(encoding="utf-8"))


def validate(st: Dict) -> List[str]:
    """Return a list of rule violations (empty means valid)."""
    errs: List[str] = []
    ids = {p["id"] for p in st["phases"]}
    for p in st["phases"]:
        if p["status"] not in PHASE_STATES:
            errs.append(f"phase {p['id']}: bad status {p['status']!r}")
        if p["status"] == PHASE_DONE and not (p.get("finished") and p.get("verified_by")):
            errs.append(f"phase {p['id']} is done but lacks finished/verified_by")
        for d in p.get("depends_on", []):
            if d not in ids:
                errs.append(f"phase {p['id']}: unknown dependency {d}")
    for c in st["components"]:
        if c["status"] not in COMP_STATES:
            errs.append(f"component {c['id']}: bad status {c['status']!r}")
        if c["status"] in ("implemented", "partial") and not (c.get("verified_by") and c.get("verified_on")):
            errs.append(f"component {c['id']} is {c['status']} but lacks verified_by/verified_on")
    for m in st.get("metrics", []):
        src = m.get("source")
        if not src:
            errs.append(f"metric {m.get('name')!r} has no source (no source, no number)")
        elif not (REPO / src).exists():
            errs.append(f"metric {m.get('name')!r}: source file {src} does not exist")
    return errs


def esc(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def header_block(st: Dict) -> str:
    phases = st["phases"]
    done = sum(1 for p in phases if p["status"] == PHASE_DONE)
    cur = next((p for p in phases if p["id"] == st["current_phase"]), None)
    envs = []
    for e in st["environments"]:
        envs.append(f"{e['name']}: {e['verified_on'] if e['status'] == 'verified' else 'not yet'}")
    return (f"Last updated: {st['updated']} | Current phase: {cur['id']}, {cur['name']} | "
            f"Overall: {done} of {len(phases)} phases done\n"
            f"Verified on: " + " | ".join(envs))


def phase_table(st: Dict) -> str:
    rows = ["| # | Phase | Status | Started | Finished |", "|---|---|---|---|---|"]
    for p in st["phases"]:
        rows.append(f"| {p['id']} | {esc(p['name'])} | {p['status']} | {p.get('started') or '-'} | {p.get('finished') or '-'} |")
    return "\n".join(rows)


def component_table(st: Dict) -> str:
    rows = ["| Component | Status | Verified by | Date | Environment |", "|---|---|---|---|---|"]
    for c in st["components"]:
        rows.append(f"| {esc(c['name'])} | {c['status']} | {('`' + esc(c['verified_by']) + '`') if c.get('verified_by') else '-'} "
                    f"| {c.get('verified_on') or '-'} | {c.get('environment') or '-'} |")
    return "\n".join(rows)


def component_tags(st: Dict) -> str:
    rows = ["| Component | Tag | Phase it lands in |", "|---|---|---|"]
    for c in st["components"]:
        rows.append(f"| {esc(c['name'])} | `{c['status']}` | {c.get('phase', '-')} |")
    return "\n".join(rows)


def metrics_table(st: Dict) -> str:
    ms = st.get("metrics", [])
    if not ms:
        return "_No measured numbers yet. Nothing is reported without a source file._"
    rows = ["| Metric | Value | Source |", "|---|---|---|"]
    for m in ms:
        rows.append(f"| {esc(m['name'])} | {esc(m['value'])} {esc(m.get('unit', ''))} | `{m['source']}` |")
    return "\n".join(rows)


def progress_mmd(st: Dict) -> str:
    out = ["flowchart LR"]
    for p in st["phases"]:
        out.append(f"  P{p['id']}[\"{p['id']}: {p['name']}\"]:::{p['status']}")
    for p in st["phases"]:
        for d in p.get("depends_on", []):
            out.append(f"  P{d} --> P{p['id']}")
    out.append(CLASS_DEFS.rstrip("\n"))
    return "\n".join(out) + "\n"


def components_mmd(st: Dict) -> str:
    out = ["flowchart TB"]
    for c in st["components"]:
        out.append(f"  {c['id']}[\"{c['name']}\"]:::{c['status']}")
    for a, b in st.get("component_links", []):
        out.append(f"  {a} --> {b}")
    out.append(CLASS_DEFS.rstrip("\n"))
    return "\n".join(out) + "\n"


def progress_block(st: Dict) -> str:
    return "```mermaid\n" + progress_mmd(st) + "```"


def components_block(st: Dict) -> str:
    return "```mermaid\n" + components_mmd(st) + "```"


BLOCKS = {
    "header": header_block,
    "phase_table": phase_table,
    "component_table": component_table,
    "component_tags": component_tags,
    "metrics": metrics_table,
    "progress_graph": progress_block,
    "components_graph": components_block,
}
# The body may be empty (marker pair on consecutive lines) or hold any number of lines.
MARKER_RE = re.compile(r"(<!-- AUTO:(?P<name>\w+) -->)\n(?:.*?\n)?(<!-- /AUTO:(?P=name) -->)", re.S)


def render_markers(text: str, st: Dict) -> str:
    def repl(m: re.Match) -> str:
        fn = BLOCKS.get(m.group("name"))
        if fn is None:
            raise SystemExit(f"unknown AUTO block: {m.group('name')}")
        return f"{m.group(1)}\n{fn(st)}\n{m.group(3)}"
    return MARKER_RE.sub(repl, text)


def planned_outputs(st: Dict) -> Dict[Path, str]:
    outs: Dict[Path, str] = {
        GRAPH_DIR / "progress.mmd": progress_mmd(st),
        GRAPH_DIR / "components_status.mmd": components_mmd(st),
    }
    for f in MARKER_FILES:
        if f.exists():
            outs[f] = render_markers(f.read_text(encoding="utf-8"), st)
    return outs


def render_svgs() -> None:
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return
    for mmd in GRAPH_DIR.glob("*.mmd"):
        try:
            subprocess.run([mmdc, "-i", str(mmd), "-o", str(mmd.with_suffix(".svg"))],
                           check=False, capture_output=True, timeout=60)
        except Exception:  # rendering must never fail the build
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if generated content is stale")
    args = ap.parse_args()

    st = load()
    errs = validate(st)
    if errs:
        print("status.json violates the documentation rules:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    stale: List[str] = []
    for path, new in planned_outputs(st).items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != new:
            stale.append(str(path.relative_to(REPO)))
            if not args.check:
                path.write_text(new, encoding="utf-8", newline="\n")

    if args.check:
        if stale:
            print("stale generated docs (run 'make docs'): " + ", ".join(stale), file=sys.stderr)
            return 1
        print("docs-check: OK")
        return 0
    render_svgs()
    print("updated: " + (", ".join(stale) if stale else "nothing (already current)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
