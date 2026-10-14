"""MRB #3914 hostile pins for FR #3909 tray/watchdog conhost --headless.

After product merge #3914:
- Get-BobiverseHeadlessPowerShellLaunch (build >= 19044 -> conhost --headless)
- Start-BobTrayInteractive uses helper for tray + watchdog; WatchdogMinutes=5
- Ensure / BobTrayLifecycle prefer Get-Process bob-tray before CIM
- Troubleshooting skill row documents blank-console steal-focus
"""
from __future__ import annotations

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INTERACTIVE = ROOT / "bob" / "scripts" / "Start-BobTrayInteractive.ps1"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobTrayRunning.ps1"
LIFECYCLE = ROOT / "bob" / "tray" / "tools" / "BobTrayLifecycle.ps1"
TROUBLE = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
PRODUCT_PIN = ROOT / "bob" / "tests" / "test_fr3909_tray_watchdog_headless.py"


def test_mrb3914_headless_helper_contiguous():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseHeadlessPowerShellLaunch" in t
    assert "FR #3909" in t
    assert "--headless" in t
    assert "conhost.exe" in t
    assert "19044" in t
    assert "conhost-headless" in t
    assert "powershell-windowstyle" in t


def test_mrb3914_interactive_watchdog_uses_helper_and_5m():
    t = INTERACTIVE.read_text(encoding="utf-8-sig")
    assert "FR #3909" in t
    assert t.count("Get-BobiverseHeadlessPowerShellLaunch") >= 2
    assert "WatchdogMinutes = 5" in t or "WatchdogMinutes=5" in t
    assert "New-ScheduledTaskAction -Execute $wdLaunch.Execute" in t or (
        "New-ScheduledTaskAction -Execute $launch.Execute" in t
    )


def test_mrb3914_ensure_lifecycle_prefer_get_process():
    ensure = ENSURE.read_text(encoding="utf-8-sig")
    assert "Get-Process" in ensure and "bob-tray" in ensure
    life = LIFECYCLE.read_text(encoding="utf-8-sig")
    assert "Get-Process" in life and "bob-tray" in life


def test_mrb3914_skill_and_product_pin():
    skill = TROUBLE.read_text(encoding="utf-8")
    assert "FR #3909" in skill
    assert "conhost.exe" in skill
    assert "BobiverseTrayWatchdog" in skill
    assert "\ufffd" not in skill
    assert not TROUBLE.read_bytes().startswith(b"\xef\xbb\xbf")
    assert PRODUCT_PIN.is_file()
