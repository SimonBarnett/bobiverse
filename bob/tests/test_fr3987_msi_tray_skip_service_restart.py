"""FR #3987: MSI Install-Bob must not race Start-Service with tray Restart-BobTrayService.

Release blocker: interactive upgrade hung when Start-BobTray -> Start-BobFleetTray
restarted ircBob while Install-Bob's Start-Service waited forever (ARP missing until
rollback). Install-time tray launch must SkipServiceRestart / BOBIVERSE_NO_SERVICE_RESTART;
CA owns the service start with a bounded wait; service start precedes live tray start.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
START_TRAY = ROOT / "bob" / "scripts" / "Start-BobTray.ps1"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
SVC_CTRL = ROOT / "bob" / "tray" / "tools" / "Invoke-BobTrayServiceControl.ps1"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr3987_start_bob_tray_accepts_skip_service_restart():
    text = _t(START_TRAY)
    assert "[switch]$SkipServiceRestart" in text
    # Pass through to Start-BobFleetTray (which already has the switch).
    assert "SkipServiceRestart" in text
    assert "-SkipServiceRestart" in text or "SkipServiceRestart:" in text


def test_fr3987_install_bob_sets_no_service_restart_for_live_tray():
    text = _t(INSTALL)
    assert "BOBIVERSE_NO_SERVICE_RESTART" in text
    assert "FR #3987" in text
    # Live interactive Start-Process must pass -SkipServiceRestart.
    assert "'-SkipServiceRestart'" in text or '"-SkipServiceRestart"' in text or "-SkipServiceRestart" in text


def test_fr3987_install_bob_starts_service_before_live_tray():
    text = _t(INSTALL)
    i_svc = text.index("Start-Service $ServiceName")
    # The interactive live Start-Process of Start-BobTray (not Startup shortcuts).
    i_tray = text.index("INFO started TipForm Start-BobTray")
    assert i_svc < i_tray, "CA must Start-Service before launching TipForm during install"


def test_fr3987_install_bob_start_service_is_bounded():
    text = _t(INSTALL)
    chunk = text[text.index("if (-not $NoStart)") : text.index("Get-Service $ServiceName")]
    assert "WaitForStatus" in chunk or "TimeoutSec" in chunk or "TimeSpan" in chunk
    # Soft-fail path kept (must not 1603 MSI forever).
    assert "WARN Start-Service" in chunk or "soft" in chunk.lower() or "catch" in chunk


def test_fr3987_svc_control_skips_start_pending():
    text = _t(SVC_CTRL)
    assert "START_PENDING" in text
    assert "FR #3987" in text


def test_fr3987_fleet_still_honours_skip_switch():
    text = _t(FLEET)
    assert "[switch]$SkipServiceRestart" in text
    assert "BOBIVERSE_NO_SERVICE_RESTART" in text
