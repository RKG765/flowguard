"""Tests for scripts/doctor.py output contract (the dashboard Settings page will parse --json)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("doctor", REPO / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor
spec.loader.exec_module(doctor)


def test_detect_env_returns_known_value():
    assert doctor.detect_env() in ("wsl", "ubuntu")


def test_result_shape():
    r = doctor.res("x", "Title", doctor.WARN, "d", "f")
    assert set(r) == {"id", "title", "status", "detail", "fix"}


def test_render_lists_fix_only_for_problems():
    rows = [doctor.res("a", "Good", doctor.PASS, "ok", "unused fix"),
            doctor.res("b", "Bad", doctor.FAIL, "broken", "do this")]
    text = doctor.render(rows, color=False)
    assert "do this" in text and "unused fix" not in text
    assert "PASS=1" in text and "FAIL=1" in text


def test_port_check_detects_busy_port(monkeypatch):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    monkeypatch.setattr(doctor, "REQUIRED_PORTS", {port: "test"})
    try:
        assert doctor.check_ports()["status"] == doctor.FAIL
    finally:
        s.close()
    assert doctor.check_ports()["status"] == doctor.PASS


def test_a_crashing_check_does_not_hide_others(monkeypatch, capsys):
    def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(doctor, "CHECKS", [boom, doctor.check_os])
    rc = doctor.main(["--json", "--quick"])
    data = json.loads(capsys.readouterr().out)
    by_id = {r["id"]: r for r in data["results"]}
    assert by_id["boom"]["status"] == doctor.FAIL and "crashed" in by_id["boom"]["detail"]
    assert "os" in by_id
    assert rc == 1


def test_json_output_contract():
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "doctor.py"), "--json", "--quick"],
                         capture_output=True, text=True)
    data = json.loads(out.stdout)
    assert data["env"] in ("wsl", "ubuntu")
    assert {r["id"] for r in data["results"]} >= {"os", "ports", "disk", "mininet"}
    assert all(set(r) == {"id", "title", "status", "detail", "fix"} for r in data["results"])


def test_cli_planned_commands_exit_2():
    r = subprocess.run([sys.executable, str(REPO / "bin" / "flowguard"), "start"], capture_output=True, text=True)
    assert r.returncode == 2 and "not implemented" in r.stderr
