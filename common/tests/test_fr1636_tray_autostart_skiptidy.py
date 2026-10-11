"""FR #1636: tray ONLOGON / shortcuts default to -SkipTidy; ForceNew only replaces the tray."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

S = ROOT / "scripts"


def _t(name: str) -> str:
    return (S / name).read_text(encoding="utf-8-sig")


def test_interactive_onlogon_and_startup_bake_skiptidy():
    t = _t("Start-BobTrayInteractive.ps1")
    assert "FR #1636" in t
    assert "ForceNew -SkipTidy" in t or "ForceNew+SkipTidy" in t
    # Persistent args still bake SkipTidy; FR #3909 routes them through $trayLaunch.
    assert "trayArgsPersistent" in t
    assert "-SkipTidy" in t
    assert "ForceNew -SkipTidy" in t
    # FR #3989: New-ScheduledTaskAction uses $trayLaunch.Argument (headless FR #3909),
    # not an inline SkipTidy string. Pin the launch object + source args.
    assert "Get-BobiverseHeadlessPowerShellLaunch" in t
    assert (
        "New-ScheduledTaskAction -Execute $trayLaunch.Execute -Argument $trayLaunch.Argument"
        in t
    )
    assert (
        "Get-BobiverseHeadlessPowerShellLaunch -PowerShellArguments $trayArgsPersistent"
        in t
    )
    # Must not leave a ForceNew-only persistent action without SkipTidy on the same line
    # (pre-#3909 shape). Post-#3909 the action line is $trayLaunch.*; SkipTidy lives in trayArgsPersistent.
    bare = [
        ln
        for ln in t.splitlines()
        if "New-ScheduledTaskAction" in ln
        and "-ForceNew" in ln
        and "SkipTidy" not in ln
        and "trayArgsPersistent" not in ln
        and "trayLaunch" not in ln
    ]
    assert not bare, bare


def test_start_menu_systray_shortcut_skiptidy():
    t = _t("Bobiverse-Common.ps1")
    assert "Add-Spec 'Start Systray'" in t
    # The Add-Spec arguments string for Start Systray includes SkipTidy
    m = re.search(r"Add-Spec 'Start Systray'.*?SkipTidy", t, re.S)
    assert m, "Start Systray shortcut must pass -SkipTidy (FR #1636)"


def test_install_bob_autostart_paths_skiptidy():
    t = _t("Install-Bob.ps1")
    assert "FR #1636" in t
    # Desktop/Startup trayArgs and HKCU Run include SkipTidy
    assert t.count("-ForceNew -SkipTidy") >= 2
    assert "BobiverseTray" in t
    # HKCU / HKU Run values must not be ForceNew-only
    run_lines = [ln for ln in t.splitlines() if "BobiverseTray" in ln or ("$runVal" in ln and "Start-BobTray" in ln)]
    joined = "\n".join(ln for ln in t.splitlines() if "$runVal" in ln)
    assert "-SkipTidy" in joined


def test_start_bobtray_writes_lifecycle_log():
    t = _t("Start-BobTray.ps1")
    assert "Write-BobTrayLifecycle" in t
    assert "tray-lifecycle.log" in t
    assert "FR #1636" in t


def test_fleet_tray_still_tidies_without_skiptidy():
    """TipForm Restart path: Start-BobFleetTray without SkipTidy still calls Stop-BobSystrayPriorAgents."""
    p = ROOT / "third_party" / "bob-tray" / "tools" / "Start-BobFleetTray.ps1"
    if not p.is_file():
        p = ROOT / "tray" / "tools" / "Start-BobFleetTray.ps1"
    text = p.read_text(encoding="utf-8-sig")
    assert "[switch]$SkipTidy" in text
    assert "Stop-BobSystrayPriorAgents" in text
    assert "if (-not $SkipTidy" in text
