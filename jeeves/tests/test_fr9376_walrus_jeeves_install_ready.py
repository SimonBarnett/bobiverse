"""FR #9376: walrus Jeeves WinRM install gate readiness + install script."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
SCRIPTS = REPO / "jeeves" / "scripts"
sys.path.insert(0, str(MON))

import walrus_jeeves_install_ready as wjir  # noqa: E402


def test_module_and_wrapper_exist():
    assert (MON / "walrus_jeeves_install_ready.py").is_file()
    assert (SCRIPTS / "Test-JeevesMonitorWalrusJeevesInstallReady.ps1").is_file()
    assert (SCRIPTS / "Install-JeevesWalrusWinRm.ps1").is_file()
    invoke = (SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "walrus_jeeves_install_ready" in invoke


def test_parse_ref_ok():
    repo, num = wjir.parse_ref("SimonBarnett/bobiverse#8833")
    assert repo == "SimonBarnett/bobiverse"
    assert num == 8833


def test_parse_ref_bad():
    try:
        wjir.parse_ref("not-a-ref")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_evaluate_gate_all_closed():
    refs = list(wjir.DEFAULT_GATE_ISSUES)
    states = {r: "CLOSED" for r in refs}
    ev = wjir.evaluate_gate(states)
    assert ev["ok"] is True
    assert ev["reason"] == "all_closed"
    assert ev["open"] == []
    assert set(ev["closed"]) == set(refs)


def test_evaluate_gate_open():
    refs = list(wjir.DEFAULT_GATE_ISSUES)
    states = {r: "CLOSED" for r in refs}
    states[refs[0]] = "OPEN"
    ev = wjir.evaluate_gate(states)
    assert ev["ok"] is False
    assert ev["reason"] == "gate_open"
    assert refs[0] in ev["open"]


def test_evaluate_gate_unknown():
    ev = wjir.evaluate_gate({"SimonBarnett/bobiverse#1": "maybe"})
    assert ev["ok"] is False
    assert ev["reason"] == "gate_unknown"
    assert ev["unknown"] == ["SimonBarnett/bobiverse#1"]


def test_fixture_all_closed(tmp_path, monkeypatch):
    refs = list(wjir.DEFAULT_GATE_ISSUES)
    fixture = tmp_path / "gate.json"
    fixture.write_text(
        json.dumps({"issues": [{"ref": r, "state": "CLOSED"} for r in refs]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_WALRUS_INSTALL_GATE_FIXTURE", str(fixture))
    monkeypatch.delenv("JEEVES_WALRUS_INSTALL_GATE_ISSUES", raising=False)
    payload, code = wjir.check(None)
    assert code == 0
    assert payload["ok"] is True
    assert payload["source"] == "fixture"
    assert payload["gate"]["reason"] == "all_closed"


def test_fixture_open_finding(tmp_path, monkeypatch):
    refs = list(wjir.DEFAULT_GATE_ISSUES)
    rows = [{"ref": r, "state": "CLOSED"} for r in refs]
    rows[0]["state"] = "OPEN"
    fixture = tmp_path / "gate.json"
    fixture.write_text(json.dumps({"issues": rows}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_WALRUS_INSTALL_GATE_FIXTURE", str(fixture))
    monkeypatch.delenv("JEEVES_WALRUS_INSTALL_GATE_ISSUES", raising=False)
    payload, code = wjir.check(None)
    assert code == 1
    assert payload["ok"] is False
    assert any("OPEN" in f for f in payload["findings"])


def test_install_script_cast_iron_pins():
    text = (SCRIPTS / "Install-JeevesWalrusWinRm.ps1").read_text(encoding="utf-8-sig")
    assert "-SiYes" in text or "$SiYes" in text
    assert "ircJeeves" in text
    assert "ErgoWalrus" in text or "Ergo" in text
    assert "ROLLBACK.ps1" in text
    assert "Bobiverse/UpdateFleet" in text
    assert "WriteDir" in text  # local stage vs remote BackupDir
    for ref in wjir.DEFAULT_GATE_ISSUES:
        assert ref in text


def test_monitor_start_lists_check():
    start = (
        REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "`walrus_jeeves_install_ready`" in start
    assert "walrus_jeeves_install_ready" in (
        SCRIPTS / "Invoke-JeevesMonitorCheck.ps1"
    ).read_text(encoding="utf-8-sig")


def test_install_script_is_bomless_ascii():
    raw = (SCRIPTS / "Install-JeevesWalrusWinRm.ps1").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("ascii")  # raises if non-ASCII
    assert "FR the build failures" in text
    assert "failed build-jeeves" in text

