# -*- coding: utf-8 -*-
"""FR #9195: pool dialog + menu; empty-online.disabled; no status BalloonTip."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
if not (TRAY / "tools" / "Watch-BobTray.ps1").is_file():
    TRAY = ROOT / "third_party" / "bob-tray"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
START = TRAY / "tools" / "BobTrayStartWorker.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9195_no_status_balloon_keeps_dialog_menu():
    w = _txt(WATCH)
    assert "FR #9195" in w
    assert "Left-click ok (FR #9186)" not in w
    assert "BalloonTip left-click proof" not in w
    assert "Invoke-BobTrayStatus" in w
    assert "Show-BobTrayCard" in w
    assert "$notify.ContextMenuStrip = $menu" in w
    assert "empty-online disabled: skip fill" in w
    assert "Test-BobTrayEmptyOnlineDisabled" in w


def test_fr9195_startworker_disabled_helper():
    s = _txt(START)
    assert "function Test-BobTrayEmptyOnlineDisabled" in s
    assert "empty-online.disabled" in s
    assert "FR #9142" in s or "FR #9195" in s
    # no-fuel skip (not fall through to auto Grok)
    assert "skip = $true" in s or "skip=$true" in s.replace(" ", "")
    assert "no-fuel" in s


@needs_ps
def test_fr9195_empty_online_disabled_zeros_fill(tmp_path: Path):
    start = START
    assert start.is_file(), start
    root = tmp_path / "bobroot"
    (root / "run" / "startworker").mkdir(parents=True)
    (root / "run" / "startworker" / "empty-online.disabled").write_text(
        "operator-starts-seats\n", encoding="utf-8"
    )
    script = tmp_path / "t9195.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
. '{start}'
$n = Get-BobTrayEmptyOnlineFillCount -LiveAgents 0 -PendingReqs 0 -SeatsOff:$false -Cooldown:$false -Cap 2 -Root '{root}'
Write-Output ('fill=' + $n)
$d = Test-BobTrayEmptyOnlineDisabled -Root '{root}'
Write-Output ('disabled=' + $d)
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert "fill=0" in lines, lines
    assert "disabled=True" in lines, lines


@needs_ps
def test_fr9195_no_fuel_skips_auto_grok(tmp_path: Path):
    start = START
    script = tmp_path / "t9195fuel.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
. '{start}'
# grok remaining 0 + free remaining 0 -> skip no-fuel (do not pin opencode or auto)
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 0 -Root '{tmp_path}'
Write-Output ('skip=' + $c.skip)
Write-Output ('reason=' + $c.reason)
Write-Output ('agent=' + $c.agent)
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert "skip=True" in lines, lines
    assert any(ln.startswith("reason=") and "no-fuel" in ln for ln in lines), lines
    assert "agent=" in "".join(lines)
