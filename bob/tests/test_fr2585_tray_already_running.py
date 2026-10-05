"""FR #2585: duplicate bob-tray must log already-running, not unexpected.

Root path must be normalized (trim quotes/slash, GetFullPath) so the
single-instance mutex matches. Start-BobFleetTray must see bob-tray.exe
without requiring Win32 ExecutablePath, and must not pass quoted --root
via Start-Process ArgumentList.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
COMMON_CS = ROOT / "bob" / "tray" / "dialogs" / "BobDialogsCommon.cs"
FLEET = ROOT / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
LIFE = ROOT / "bob" / "tray" / "tools" / "BobTrayLifecycle.ps1"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobTrayRunning.ps1"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr2585_common_root_normalizes_quotes_and_slash():
    t = _read(COMMON_CS)
    assert "GetFullPath" in t
    # Must strip embedded quotes from --root (Start-Process ArgumentList footgun).
    assert 'Trim(\'"\')' in t or "Trim('\"')" in t or 'Trim(\'")' in t or 'Trim(\'"' in t
    assert "TrimEnd" in t
    assert "TrayMutexKey" in t
    assert "NormalizeRoot" in t


def test_fr2585_bob_tray_logs_already_running_when_single_fails():
    t = _read(BOB_TRAY)
    assert "already-running" in t
    body = t[t.find("static int Main") :]
    # already-running path must run before tray-up.
    fail_idx = body.find("already-running")
    up_idx = body.find('Write("tray-up"')
    if up_idx < 0:
        up_idx = body.find('Write("tray-up"')
    assert fail_idx >= 0
    assert up_idx > fail_idx
    assert "unexpected" in body


def test_fr2585_fleet_detects_bob_tray_without_executablepath():
    t = _read(FLEET)
    fn = t[t.find("function Get-BobSystrayTrayProcesses") :]
    fn = fn[: fn.find("\nfunction ")] if "\nfunction " in fn[1:] else fn
    assert "bob-tray.exe" in fn
    # Must not require ExecutablePath for Name -eq bob-tray.exe match.
    assert not re.search(
        r"Name\s+-eq\s+'bob-tray\.exe'\s+-and\s+\$_\.ExecutablePath",
        fn,
    )


def test_fr2585_fleet_start_process_root_unquoted():
    t = _read(FLEET)
    # Footgun: ArgumentList @('--root', ('"{0}"' -f $RepoRoot)) embeds quotes in argv.
    assert "('{0}\"'" not in t.replace(" ", "")
    assert "@('--root', $RepoRoot)" in t or '@("--root", $RepoRoot)' in t
    assert "Start-Process -FilePath $trayExe -ArgumentList $spArgs" in t


def test_fr2585_ensure_and_lifecycle_ignore_already_running_as_crash():
    life = _read(LIFE)
    ensure = _read(ENSURE)
    assert "bob-tray.exe" in ensure
    # Watchdog relaunches only when process absent; document already-running.
    assert "ForceNew" in ensure and "SkipTidy" in ensure
    assert "already-running" in life or "already-running" in ensure or "FR #2585" in life
