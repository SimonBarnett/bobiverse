"""FR #1642: tray unexpected-exit watchdog relaunches with ForceNew+SkipTidy only."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_SCR = ROOT / "bob" / "scripts"
BOB_TOOLS = ROOT / "bob" / "tray" / "tools"
COMMON_SCR = ROOT / "scripts"


def _read(*cands: Path) -> str:
    for p in cands:
        if p.is_file():
            return p.read_text(encoding="utf-8-sig")
    raise FileNotFoundError(cands)


def test_ensure_bob_tray_running_skiptidy_only():
    t = _read(BOB_SCR / "Ensure-BobTrayRunning.ps1", COMMON_SCR / "Ensure-BobTrayRunning.ps1")
    assert "FR #1642" in t
    assert "ForceNew" in t and "SkipTidy" in t
    assert "-ForceNew -SkipTidy" in t
    assert "Test-BobTrayWatchdogSuppressed" in t
    assert not any(
        "Stop-BobSystrayPriorAgents.ps1" in ln
        for ln in t.splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert "watchdog-relaunch" in t
    assert "BOBIVERSE_TRAY_WATCHDOG" in t


def test_interactive_registers_watchdog_task():
    t = _read(
        BOB_SCR / "Start-BobTrayInteractive.ps1",
        COMMON_SCR / "Start-BobTrayInteractive.ps1",
    )
    assert "BobiverseTrayWatchdog" in t
    assert "Ensure-BobTrayRunning.ps1" in t
    assert "FR #1642" in t
    assert "WatchdogMinutes" in t


def test_lifecycle_helpers_shared():
    t = _read(BOB_TOOLS / "BobTrayLifecycle.ps1")
    assert "Write-BobTrayLifecycleEvent" in t
    assert "Set-BobTrayWatchdogSuppress" in t
    assert "Clear-BobTrayWatchdogSuppress" in t
    assert "Test-BobTrayProcessPresent" in t
    assert "tray-lifecycle.log" in t
    assert "tray-watchdog.suppress" in t


def test_watch_bob_tray_logs_exit_and_suppresses_intentional_exit():
    t = _read(BOB_TOOLS / "Watch-BobTray.ps1")
    assert "Write-BobTrayLifecycleEvent" in t
    assert "Set-BobTrayWatchdogSuppress" in t
    assert "process-exit" in t
    assert "trayExitReason = 'Restart'" in t or '$script:trayExitReason = ''Restart''' in t


def test_bob_tray_cs_writes_lifecycle_and_suppress():
    t = _read(ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs")
    assert "TrayLifecycle" in t
    assert "tray-lifecycle.log" in t
    assert "SuppressWatchdog" in t
    assert "tray-watchdog.suppress" in t
    assert "process-exit" in t


def test_start_bobtray_clears_suppress_on_start():
    t = _read(BOB_SCR / "Start-BobTray.ps1", COMMON_SCR / "Start-BobTray.ps1")
    assert "Clear-BobTrayWatchdogSuppress" in t
    assert "Write-BobTrayLifecycle" in t or "Write-BobTrayLifecycleEvent" in t
