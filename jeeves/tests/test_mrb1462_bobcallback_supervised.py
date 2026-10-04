"""Hostile MRB #1462 / FR #1455: BobCallback supervised restart wiring."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SUP = ROOT / "common" / "scripts" / "Start-BobCallbackSupervised.ps1"
JEEVES_SUP = ROOT / "jeeves" / "scripts" / "Start-BobCallbackSupervised.ps1"
JEEVES_REG = ROOT / "jeeves" / "scripts" / "Register-BobCallbackTask.ps1"
COMMON_REG = ROOT / "common" / "scripts" / "Register-BobCallbackTask.ps1"


def test_supervised_script_in_common_and_jeeves():
    """Compose unions both trees; Register from jeeves/scripts must also find the wrapper."""
    assert COMMON_SUP.is_file(), f"missing {COMMON_SUP}"
    assert JEEVES_SUP.is_file(), f"missing {JEEVES_SUP} (Register `$here` lookup)"


def test_supervised_is_restart_loop():
    text = COMMON_SUP.read_text(encoding="utf-8-sig")
    assert "while ($true)" in text or "while($true)" in text
    assert "Start-Process" in text
    assert "Wait-Process" in text
    assert "RestartDelaySec" in text
    assert "bobcallback" in text.lower()


def test_supervised_stops_child_on_wrapper_exit():
    """Task stop must not leave an orphan bobcallback.py (MRB #1462)."""
    text = COMMON_SUP.read_text(encoding="utf-8-sig")
    assert "Stop-Process" in text or "Kill" in text
    assert "finally" in text.lower() or "trap" in text.lower() or "try" in text.lower()


def test_register_prefers_supervised_action():
    for path in (JEEVES_REG, COMMON_REG):
        text = path.read_text(encoding="utf-8-sig")
        assert "Start-BobCallbackSupervised.ps1" in text
        assert "powershell.exe" in text
        assert "Refuse RunAsUser" in text or "S-1-5-18" in text  # keep FR #1316 / #1357 gate
