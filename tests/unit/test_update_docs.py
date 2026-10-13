"""Tests for scripts/update_docs.py: the evidence rules and marker rendering."""
import copy
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("update_docs", REPO / "scripts" / "update_docs.py")
ud = importlib.util.module_from_spec(spec)
sys.modules["update_docs"] = ud
spec.loader.exec_module(ud)


def base_state():
    return {
        "updated": "2026-01-01",
        "current_phase": 0,
        "environments": [{"name": "WSL2", "status": "verified", "verified_on": "2026-01-01"}],
        "phases": [
            {"id": 0, "name": "Spike", "status": "in_progress", "started": "2026-01-01", "depends_on": []},
            {"id": 1, "name": "L1", "status": "not_started", "depends_on": [0]},
        ],
        "components": [{"id": "c1", "name": "Doctor", "status": "planned", "phase": 0}],
        "metrics": [],
    }


def test_valid_state_has_no_errors():
    assert ud.validate(base_state()) == []


def test_implemented_component_requires_verification():
    st = base_state()
    st["components"][0]["status"] = "implemented"
    errs = ud.validate(st)
    assert any("verified_by" in e for e in errs)
    st["components"][0].update(verified_by="make test", verified_on="2026-01-01")
    assert ud.validate(st) == []


def test_done_phase_requires_evidence():
    st = base_state()
    st["phases"][0]["status"] = "done"
    assert any("done but lacks" in e for e in ud.validate(st))


def test_metric_needs_existing_source():
    st = base_state()
    st["metrics"] = [{"name": "x", "value": 1}]
    assert any("no source" in e for e in ud.validate(st))
    st["metrics"] = [{"name": "x", "value": 1, "source": "does/not/exist.json"}]
    assert any("does not exist" in e for e in ud.validate(st))
    st["metrics"] = [{"name": "x", "value": 1, "source": "README.md"}]
    assert ud.validate(st) == []


def test_unknown_dependency_and_bad_status_rejected():
    st = base_state()
    st["phases"][1]["depends_on"] = [9]
    st["components"][0]["status"] = "great"
    errs = ud.validate(st)
    assert any("unknown dependency" in e for e in errs)
    assert any("bad status" in e for e in errs)


def test_marker_block_is_replaced_and_idempotent():
    st = base_state()
    text = "intro\n<!-- AUTO:phase_table -->\nSTALE\n<!-- /AUTO:phase_table -->\noutro\n"
    once = ud.render_markers(text, st)
    assert "STALE" not in once and "| 0 | Spike |" in once
    assert ud.render_markers(once, st) == once
    assert once.startswith("intro\n") and once.endswith("outro\n")


def test_empty_marker_block_is_filled():
    """Regression: a marker pair on consecutive lines used to be skipped, so docs-check passed on unfilled docs."""
    st = base_state()
    text = "<!-- AUTO:phase_table -->\n<!-- /AUTO:phase_table -->\n"
    out = ud.render_markers(text, st)
    assert "| 0 | Spike |" in out
    assert ud.render_markers(out, st) == out


def test_real_docs_have_no_unfilled_marker_blocks():
    for f in ud.MARKER_FILES:
        if f.exists():
            for m in ud.MARKER_RE.finditer(f.read_text(encoding="utf-8")):
                body = m.group(0).split("\n")[1:-1]
                assert body, f"{f.name}: block {m.group('name')} is empty after generation"


def test_unknown_marker_aborts():
    with pytest.raises(SystemExit):
        ud.render_markers("<!-- AUTO:nope -->\nx\n<!-- /AUTO:nope -->", base_state())


def test_mermaid_graphs_reference_every_node():
    st = base_state()
    prog = ud.progress_mmd(st)
    assert "P0[" in prog and "P0 --> P1" in prog and ":::in_progress" in prog
    assert "c1[" in ud.components_mmd(st)


def test_real_status_json_is_valid_and_docs_current():
    """Same guarantee as `make docs-check`: the committed docs equal what status.json generates."""
    st = ud.load()
    assert ud.validate(copy.deepcopy(st)) == []
    for path, expected in ud.planned_outputs(st).items():
        assert path.read_text(encoding="utf-8") == expected, f"{path.name} is stale; run `make docs`"
