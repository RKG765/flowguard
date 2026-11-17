"""PDF report writer: a structurally valid file, escaped text, page breaks, honest empty sections."""
import re

from core.pdf import build_report, wrap


def check_structure(data: bytes) -> int:
    """Every xref entry points at its 'N 0 obj', startxref points at the table, the page count matches /Count."""
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)\n%%EOF", data).group(1))
    assert data[start:start + 4] == b"xref"
    n = int(re.search(rb"xref\n0 (\d+)\n", data[start:]).group(1))
    entries = re.findall(rb"(\d{10}) 00000 n ", data[start:])
    assert len(entries) == n - 1
    for num, off in enumerate(entries, 1):
        assert data[int(off):].startswith(f"{num} 0 obj".encode()), num
    return int(re.search(rb"/Count (\d+)", data).group(1))


SUMMARY = {"generated_at": 1_700_000_000, "alerts_total": 3, "alerts_by_kind": {"forged": 2, "missing": 1}, "alerts_by_severity": {"high": 3},
           "open_incidents": 1, "detect_latency_ms": {"n": 3, "mean": 16.2, "median": 16.1, "p95": 16.6}, "time_to_restore_ms": None}


def test_empty_report_is_valid_and_says_nothing_was_recorded():
    data = build_report({"alerts_total": 0, "alerts_by_kind": {}, "open_incidents": 0, "detect_latency_ms": None, "time_to_restore_ms": None}, [], [], "admin")
    assert check_structure(data) == 1
    assert b"No alerts recorded." in data and b"no data" in data and b"none recorded" in data


def test_hostile_text_is_escaped_and_cannot_break_the_file():
    nasty = "(evil) \\ ) ET Q stream endobj \u20ac \u4e2d\n\r"
    data = build_report(SUMMARY, [], [{"id": 1, "severity": "high", "status": "open", "dpid": None, "alert_count": 1, "title": nasty}], nasty)
    check_structure(data)
    assert b"\\(evil\\)" in data and b"(evil) " not in data


def test_many_rows_flow_onto_more_pages_and_stay_valid():
    alerts = [{"t": 1_700_000_000 + i, "kind": "forged", "severity": "high", "layer": "L1", "priority": 300, "action": "removed",
               "detect_latency_ms": 16.1, "time_to_restore_ms": 12.0} for i in range(200)]
    data = build_report(SUMMARY, alerts, [], "admin")
    assert check_structure(data) >= 4


def test_wrap_never_returns_a_line_longer_than_the_width():
    for line in wrap("word " * 50 + "x" * 200, 40):
        assert len(line) <= 40
    assert wrap("", 10) == [""]
