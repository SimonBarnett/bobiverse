"""Hostile MRB #3993 / FR #3987: MSI Install-Bob must not race tray Restart-BobTrayService.

Pins order (Start-Service before TipForm), bounded WaitForStatus, env suppress + restore,
interactive -SkipServiceRestart, and START_PENDING skip in service control.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
START_TRAY = ROOT / "bob" / "scripts" / "Start-BobTray.ps1"
SVC_CTRL = ROOT / "bob" / "tray" / "tools" / "Invoke-BobTrayServiceControl.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb3993_hostile_start_service_before_tipform_info():
    text = _t(INSTALL)
    i_wait = text.index("WaitForStatus")
    i_tip = text.index("INFO started TipForm Start-BobTray")
    assert i_wait < i_tip


def test_mrb3993_hostile_waitforstatus_sixty_seconds():
    text = _t(INSTALL)
    assert "FromSeconds(60)" in text or "FromSeconds(60)" in text.replace(" ", "")
    assert "ServiceControllerStatus]::Running" in text or "ServiceControllerStatus.Running" in text


def test_mrb3993_hostile_env_set_before_tray_and_restored_in_finally():
    text = _t(INSTALL)
    i_env = text.index("BOBIVERSE_NO_SERVICE_RESTART")
    i_try = text.index("try {", i_env)
    i_finally = text.index("finally {", i_try)
    chunk = text[i_env:i_finally]
    assert "= '1'" in chunk or '= "1"' in chunk
    fin = text[i_finally : i_finally + 400]
    assert "Remove-Item Env:\\BOBIVERSE_NO_SERVICE_RESTART" in fin or "BOBIVERSE_NO_SERVICE_RESTART" in fin


def test_mrb3993_hostile_interactive_argumentlist_has_skip():
    text = _t(INSTALL)
    # ArgumentList array for live interactive Start-Process
    assert "'-SkipServiceRestart'" in text or '"-SkipServiceRestart"' in text


def test_mrb3993_hostile_start_bob_tray_passes_fleet_switch():
    text = _t(START_TRAY)
    assert "[switch]$SkipServiceRestart" in text
    assert "SkipServiceRestart:$noSvcRestart" in text


def test_mrb3993_hostile_svc_control_exits_on_start_pending():
    text = _t(SVC_CTRL)
    i = text.index("START_PENDING")
    window = text[i : i + 280]
    assert "STOP_PENDING" in window
    assert "exit 0" in window
    assert "FR #3987" in window


def test_mrb3993_hostile_fleet_gate_still_present():
    text = _t(FLEET)
    assert "[switch]$SkipServiceRestart" in text
    assert "BOBIVERSE_NO_SERVICE_RESTART" in text
    assert "Restart-BobTrayService" in text
