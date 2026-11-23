# -*- coding: utf-8 -*-
"""FR #9178: TipForm tip/menu must not park off-screen from stale iconRect."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
if not (TRAY / "src" / "Public" / "Get-BobTrayHover.ps1").is_file():
    TRAY = ROOT / "third_party" / "bob-tray"
HOVER = TRAY / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9178_hover_has_onscreen_helpers():
    h = _txt(HOVER)
    assert "function Test-BobTrayRectIntersectsAny" in h
    assert "function Get-BobTrayCursorTipPlacement" in h
    assert "FR #9178" in h
    assert "cursor-stale-icon" in h
    # Stale icon outside WorkingArea must be dropped before icon placement.
    fn = h[h.index("function Get-BobTrayTipPlacement") : h.index("function Get-BobTrayTipPlacement") + 4500]
    assert "Test-BobTrayRectIntersectsAny" in fn
    assert "ScreenAreas" in fn


def test_fr9178_watch_uidiag_and_relocate_wiring():
    w = _txt(WATCH)
    assert "function Write-BobTrayUiDiag" in w
    assert "function Test-BobTrayTipOnScreen" in w
    assert "function Move-BobTrayTipToCursor" in w
    assert "TipRelocateCursor" in w
    assert "TipOnScreenCheck" in w
    assert "MenuForceShowAtCursor" in w
    assert "Add_Opened" in w
    assert "Add_Opening" in w
    assert "MouseDown" in w
    assert "after-tip-show" in w
    assert "ScreenAreas" in w
    card_start = w.index("function Show-BobTrayCard")
    card_end = w.index("\nfunction ", card_start + 1)
    card = w[card_start:card_end]
    assert "Test-BobTrayTipOnScreen" in card
    assert "Move-BobTrayTipToCursor" in card or "TipRelocateCursor" in card
    assert "after-tip-show" in card
    assert "Write-BobTrayUiDiag" in card
    assert "ScreenAreas" in card


@needs_ps
def test_fr9178_stale_icon_uses_cursor_placement(tmp_path: Path):
    """iconRect far outside WorkArea -> source cursor-stale-icon; tip inside WorkArea."""
    psd1 = TRAY / "src" / "BobBridge.psd1"
    assert psd1.is_file(), psd1
    script = tmp_path / "t9178.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
Import-Module '{psd1}' -Force -DisableNameChecking
& (Get-Module BobBridge) {{
  $work = [pscustomobject]@{{ X = 0; Y = 0; Width = 1920; Height = 1080 }}
  $stale = [pscustomobject]@{{ X = 8000; Y = 8000; Width = 32; Height = 32 }}
  $cursor = [pscustomobject]@{{ X = 100; Y = 100 }}
  $p = Get-BobTrayTipPlacement -TipWidth 420 -TipHeight 121 `
    -IconRect $stale -Cursor $cursor -WorkArea $work -AlreadyVisible $false
  Write-Output ('src=' + $p.source)
  Write-Output ('x=' + $p.x)
  Write-Output ('y=' + $p.y)
  $hit = Test-BobTrayRectIntersectsAny -Rect ([pscustomobject]@{{
    X = [int]$p.x; Y = [int]$p.y; Width = 420; Height = 121
  }}) -Areas @($work)
  Write-Output ('on=' + $hit)
  $miss = Test-BobTrayRectIntersectsAny -Rect $stale -Areas @($work)
  Write-Output ('staleOn=' + $miss)
}}
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert any(ln == "src=cursor-stale-icon" for ln in lines), lines
    assert any(ln == "on=True" for ln in lines), lines
    assert any(ln == "staleOn=False" for ln in lines), lines


@needs_ps
def test_fr9178_icon_on_work_still_icon_source(tmp_path: Path):
    psd1 = TRAY / "src" / "BobBridge.psd1"
    script = tmp_path / "t9178b.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
Import-Module '{psd1}' -Force -DisableNameChecking
& (Get-Module BobBridge) {{
  $work = [pscustomobject]@{{ X = 0; Y = 0; Width = 1920; Height = 1080 }}
  $icon = [pscustomobject]@{{ X = 1800; Y = 1040; Width = 32; Height = 32 }}
  $cursor = [pscustomobject]@{{ X = 1810; Y = 1050 }}
  $p = Get-BobTrayTipPlacement -TipWidth 420 -TipHeight 121 `
    -IconRect $icon -Cursor $cursor -WorkArea $work -AlreadyVisible $false
  Write-Output ('src=' + $p.source)
}}
"""
    script.write_text(body, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert any(ln == "src=icon" for ln in lines), lines
