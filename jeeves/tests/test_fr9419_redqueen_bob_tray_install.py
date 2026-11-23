"""FR #9419: Install-BobTrayRedqueen resolve/hash/DryRun + monitor readiness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
JEEVES_SCRIPTS = REPO / "jeeves" / "scripts"
BOB_SCRIPTS = REPO / "bob" / "scripts"
sys.path.insert(0, str(MON))

import redqueen_bob_tray_install_ready as rbtir  # noqa: E402


def test_module_and_scripts_exist():
    assert (MON / "redqueen_bob_tray_install_ready.py").is_file()
    assert (JEEVES_SCRIPTS / "Test-JeevesMonitorRedqueenBobTrayInstallReady.ps1").is_file()
    assert (BOB_SCRIPTS / "Install-BobTrayRedqueen.ps1").is_file()
    invoke = (JEEVES_SCRIPTS / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "redqueen_bob_tray_install_ready" in invoke


def test_pick_manifest_exe_hash():
    man = {
        "files": {
            "bob-tray.exe": "aa" * 32,
            "tools/bob-tray.exe": "bb" * 32,
            "src/Public/Get-BobTrayHover.ps1": "cc" * 32,
        }
    }
    assert rbtir.pick_manifest_exe_hash(man) == "aa" * 32
    man2 = {"files": {"tools/bob-tray.exe": "dd" * 32}}
    assert rbtir.pick_manifest_exe_hash(man2) == "dd" * 32


def test_pick_manifest_exe_hash_missing():
    try:
        rbtir.pick_manifest_exe_hash({"files": {}})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_evaluate_drift_match():
    ev = rbtir.evaluate_drift(expected="ab" * 32, live="AB" * 32)
    assert ev["ok"] is True
    assert ev["reason"] == "match"
    assert ev["drift"] is False


def test_evaluate_drift_mismatch():
    ev = rbtir.evaluate_drift(expected="aa" * 32, live="bb" * 32)
    assert ev["ok"] is False
    assert ev["reason"] == "drift"
    assert ev["drift"] is True


def test_evaluate_drift_missing_live():
    ev = rbtir.evaluate_drift(expected="aa" * 32, live="")
    assert ev["ok"] is False
    assert ev["reason"] == "live_missing"


def test_fixture_match(tmp_path, monkeypatch):
    fixture = tmp_path / "tray.json"
    fixture.write_text(
        json.dumps(
            {
                "run_id": "45200032562",
                "bob_tray_sha256": "aa" * 32,
                "live_sha256": "aa" * 32,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_TRAY_REDQUEEN_INSTALL_FIXTURE", str(fixture))
    payload, code = rbtir.check(None)
    assert code == 0
    assert payload["ok"] is True
    assert payload["source"] == "fixture"
    assert payload["drift"]["reason"] == "match"


def test_fixture_drift_finding(tmp_path, monkeypatch):
    fixture = tmp_path / "tray.json"
    fixture.write_text(
        json.dumps(
            {
                "run_id": "45200032562",
                "bob_tray_sha256": "aa" * 32,
                "live_sha256": "bb" * 32,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_TRAY_REDQUEEN_INSTALL_FIXTURE", str(fixture))
    payload, code = rbtir.check(None)
    assert code == 1
    assert payload["ok"] is False
    assert any("drift" in f.lower() for f in payload["findings"])


def test_install_script_cast_iron_pins():
    text = (BOB_SCRIPTS / "Install-BobTrayRedqueen.ps1").read_text(encoding="utf-8-sig")
    assert "build-bob-tray.yml" in text
    assert "bob-tray" in text
    assert "ROLLBACK.ps1" in text
    assert "Install-BobTrayHotpatch" in text
    assert "DryRun" in text or "$DryRun" in text
    assert "-Install" in text or "$Install" in text
    for banned in ("ircBob", "Ergo", "BobIrcd", "CredMan"):
        assert banned in text  # listed in never-touch
    assert "never" in text.lower()


def test_install_script_is_bomless_ascii():
    raw = (BOB_SCRIPTS / "Install-BobTrayRedqueen.ps1").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("ascii")  # raises if non-ASCII
    assert "FR the build" in text or "failed build-bob-tray" in text
    assert "hash mismatch" in text.lower() or "Hash mismatch" in text


def test_monitor_start_lists_check():
    start = (
        REPO / "jeeves" / ".grok" / "skills" / "monitor-start" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "`redqueen_bob_tray_install_ready`" in start
