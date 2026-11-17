"""A small PDF writer and the FlowGuard report layout (standard library only).

Enough PDF for a report: text in two built-in fonts, filled rectangles (bar charts, header band), rules, and automatic page
breaks. Text is limited to Latin-1 (anything else becomes '?'), and every string is escaped, so alert text coming from the
engine can never break the file. The layout draws only what it is given: empty sections say so, nothing is invented.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

PAGE_W, PAGE_H, MARGIN = 595, 842, 40
INK, MUTED, RULE = (0.11, 0.12, 0.15), (0.38, 0.40, 0.44), (0.80, 0.78, 0.72)
BLUE, GREEN, ORANGE, RED = (0.12, 0.42, 0.65), (0.08, 0.45, 0.22), (0.80, 0.45, 0.05), (0.72, 0.10, 0.20)
KIND_INK = {"altered": RED, "forged": RED, "shadow": RED, "missing": ORANGE, "unattributed_change": ORANGE, "probe_failed": ORANGE}


def _esc(s: Any) -> str:
    t = str(s).encode("latin-1", "replace").decode("latin-1")
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\r", " ").replace("\n", " ")


def wrap(text: str, width: int) -> List[str]:
    """Greedy word wrap by character count (Helvetica averages about half the font size per character)."""
    out, line = [], ""
    for word in str(text).split():
        while len(word) > width:  # a single very long token is cut, never allowed to run off the page
            if line:
                out.append(line)
                line = ""
            out.append(word[:width])
            word = word[width:]
        if len(line) + len(word) + (1 if line else 0) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


class Pdf:
    def __init__(self, footer: str = "") -> None:
        self.pages: List[List[str]] = []
        self.footer = footer
        self.y = 0.0
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def ensure(self, h: float) -> None:
        if self.y - h < MARGIN + 18:
            self._new_page()

    def _cmd(self, s: str) -> None:
        self.pages[-1].append(s)

    def rect(self, x: float, y: float, w: float, h: float, rgb: Tuple[float, float, float]) -> None:
        self._cmd(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def hline(self, y: float, rgb: Tuple[float, float, float] = RULE) -> None:
        self._cmd(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG 0.6 w {MARGIN} {y:.1f} m {PAGE_W - MARGIN} {y:.1f} l S")

    def text(self, x: float, y: float, s: Any, size: float = 10, bold: bool = False, rgb: Tuple[float, float, float] = INK) -> None:
        self._cmd(f"BT /F{2 if bold else 1} {size} Tf {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {x:.1f} {y:.1f} Td ({_esc(s)}) Tj ET")

    def line(self, s: Any, size: float = 10, bold: bool = False, rgb: Tuple[float, float, float] = INK, gap: float = 3) -> None:
        self.ensure(size + gap)
        self.y -= size
        self.text(MARGIN, self.y, s, size, bold, rgb)
        self.y -= gap

    def paragraph(self, s: str, size: float = 10, rgb: Tuple[float, float, float] = INK) -> None:
        for ln in wrap(s, int((PAGE_W - 2 * MARGIN) / (size * 0.5))):
            self.line(ln, size, rgb=rgb)

    def heading(self, s: str) -> None:
        self.ensure(40)
        self.y -= 10
        self.line(s.upper(), 11, bold=True, rgb=BLUE, gap=2)
        self.hline(self.y)
        self.y -= 6

    def table(self, head: Sequence[str], rows: Iterable[Sequence[Any]], widths: Sequence[float]) -> None:
        size = 8.5

        def row(cells: Sequence[Any], bold: bool, rgb: Tuple[float, float, float] = INK) -> None:
            self.ensure(size + 6)
            self.y -= size + 2
            x = MARGIN
            for c, w in zip(cells, widths):
                self.text(x, self.y, str(c)[: max(1, int(w / (size * 0.52)))], size, bold, rgb)
                x += w
            self.y -= 3

        row(head, True, MUTED)
        self.hline(self.y + 1)
        n = 0
        for r in rows:
            row(r, False)
            n += 1
        if not n:
            self.line("none recorded", 9, rgb=MUTED)

    def build(self) -> bytes:
        objs: List[bytes] = []

        def add(b: str) -> int:
            objs.append(b.encode("latin-1"))
            return len(objs)

        add("<< /Type /Catalog /Pages 2 0 R >>")                                                          # 1
        add("")                                                                                             # 2 (filled below)
        add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")          # 3
        add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")     # 4
        kids = []
        total = len(self.pages)
        for i, cmds in enumerate(self.pages, 1):
            foot = f"BT /F1 8 Tf {MUTED[0]} {MUTED[1]} {MUTED[2]} rg {MARGIN} 24 Td ({_esc(self.footer)}   page {i} of {total}) Tj ET"
            body = "\n".join(cmds + [foot])
            content = add(f"<< /Length {len(body.encode('latin-1', 'replace'))} >>\nstream\n{body}\nendstream")
            page = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content} 0 R >>")
            kids.append(f"{page} 0 R")
        objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("latin-1")
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for n, o in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{n} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def _stat(s: Any) -> str:
    return "no data" if not s else f"median {s['median']} ms   mean {s['mean']} ms   95th pct {s['p95']} ms   n={s['n']}"


def build_report(summary: Dict[str, Any], alerts: Sequence[Dict[str, Any]], incidents: Sequence[Dict[str, Any]], who: str) -> bytes:
    """The FlowGuard report: key numbers, alerts by kind (bars), latencies, incidents, latest alerts."""
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(summary.get("generated_at") or time.time()))
    pdf = Pdf(footer=f"FlowGuard report {when}. Computed only from stored alerts; empty sections are empty, nothing is invented.")
    pdf.rect(0, PAGE_H - 70, PAGE_W, 70, (0.09, 0.14, 0.21))
    pdf.text(MARGIN, PAGE_H - 38, "FLOWGUARD", 22, True, (0.92, 0.91, 0.86))
    pdf.text(MARGIN, PAGE_H - 56, "SDN flow-rule integrity report", 10, False, (0.70, 0.75, 0.82))
    pdf.text(PAGE_W - 230, PAGE_H - 38, f"generated {when}", 9, False, (0.70, 0.75, 0.82))
    pdf.text(PAGE_W - 230, PAGE_H - 52, f"by {who}", 9, False, (0.70, 0.75, 0.82))
    pdf.y = PAGE_H - 92

    pdf.heading("Key figures")
    boxes = [("Alerts recorded", summary.get("alerts_total", 0)), ("Open incidents", summary.get("open_incidents", 0)),
             ("Median detect", f"{summary['detect_latency_ms']['median']} ms" if summary.get("detect_latency_ms") else "no data"),
             ("Median restore", f"{summary['time_to_restore_ms']['median']} ms" if summary.get("time_to_restore_ms") else "no data")]
    bw = (PAGE_W - 2 * MARGIN - 3 * 10) / 4
    top = pdf.y
    for i, (label, value) in enumerate(boxes):
        x = MARGIN + i * (bw + 10)
        pdf.rect(x, top - 52, bw, 52, (0.94, 0.93, 0.89))
        pdf.text(x + 8, top - 16, label.upper(), 7.5, True, MUTED)
        pdf.text(x + 8, top - 40, value, 16, True, INK)
    pdf.y = top - 62

    pdf.heading("Alerts by kind")
    kinds = sorted((summary.get("alerts_by_kind") or {}).items(), key=lambda kv: -kv[1])
    if not kinds:
        pdf.line("No alerts recorded.", 9, rgb=MUTED)
    mx = max([n for _, n in kinds] or [1])
    for kind, n in kinds:
        pdf.ensure(16)
        pdf.y -= 12
        pdf.text(MARGIN, pdf.y, kind.replace("_", " "), 9)
        pdf.rect(MARGIN + 130, pdf.y - 2, max(2.0, 300.0 * n / mx), 10, KIND_INK.get(kind, BLUE))
        pdf.text(MARGIN + 440, pdf.y, n, 9, True)
        pdf.y -= 4
    sev = summary.get("alerts_by_severity") or {}
    if sev:
        pdf.line("By severity: " + ", ".join(f"{k} {v}" for k, v in sorted(sev.items())), 9, rgb=MUTED)

    pdf.heading("Latency (engine side, monitor event to classification and to restore)")
    pdf.line("Detect:  " + _stat(summary.get("detect_latency_ms")), 9)
    pdf.line("Restore: " + _stat(summary.get("time_to_restore_ms")), 9)

    pdf.heading("Incidents (most recently updated)")
    pdf.table(["#", "Severity", "Status", "Switch", "Alerts", "Title"],
              [(i["id"], i["severity"], i["status"], i.get("dpid") or "-", i["alert_count"], i["title"]) for i in incidents],
              [28, 55, 70, 110, 40, 190])

    pdf.heading("Latest alerts")
    pdf.table(["Time", "Kind", "Sev.", "Layer", "Prio", "Action", "Detect ms", "Restore ms"],
              [(time.strftime("%m-%d %H:%M:%S", time.localtime(a["t"])), a["kind"], a["severity"], a["layer"], a.get("priority") if a.get("priority") is not None else "-",
                a.get("action") or "-", a.get("detect_latency_ms") if a.get("detect_latency_ms") is not None else "-",
                a.get("time_to_restore_ms") if a.get("time_to_restore_ms") is not None else "-") for a in alerts],
              [78, 100, 48, 40, 40, 70, 62, 62])
    return pdf.build()
