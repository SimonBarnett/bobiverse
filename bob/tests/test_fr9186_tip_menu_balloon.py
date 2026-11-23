# -*- coding: utf-8 -*-
"""FR #9186: TipForm TopMost must not block menu; empty Left is irBad; BalloonTip proof."""
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


def test_fr9186_hover_rejects_empty_left():
    h = _txt(HOVER)
    assert "FR #9186" in h
    # Incomplete Left/X must be rejected (irBad) before icon placement.
    assert "Test-BobTrayIconRectUsable" in h or "irBad" in h
    fn = h[h.index("function ConvertTo-BobTrayRect") : h.index("function ConvertTo-BobTrayRect") + 1200]
    assert "return $null" in fn


def test_fr9186_watch_cursor_forced_balloon_hide():
    w = _txt(WATCH)
    assert "FR #9186" in w
    # Park tip with cursor-forced placement (no iconRect).
    card_start = w.index("function Show-BobTrayCard")
    card_end = w.index("\nfunction ", card_start + 1)
    card = w[card_start:card_end]
    assert "cursor-forced" in card or "Get-BobTrayCursorTipPlacement" in card
    assert "IconRect $null" in card or "-IconRect $null" in card
    # BalloonTip proof on left-click.
    assert "ShowBalloonTip" in w
    assert "BalloonTip" in w or "balloon" in w.lower()
    # Hide tip before menu; Opening must clear TopMost tip.
    open_idx = w.index("Add_Opening")
    open_snip = w[open_idx : open_idx + 900]
    assert "Hide-BobTrayCard" in open_snip
    assert "TipHiddenForMenu" in w or "TopMost" in open_snip or "TryHide" in w
    hide_start = w.index("function Hide-BobTrayCard")
    hide = w[hide_start : hide_start + 800]
    assert "TopMost" in hide or "TryHide" in hide


@needs_ps
def test_fr9186_empty_left_not_icon_source(tmp_path: Path):
    """Empty Left + Width set must not yield src=icon (irBad)."""
    psd1 = TRAY / "src" / "BobBridge.psd1"
    assert psd1.is_file(), psd1
    script = tmp_path / "t9186.ps1"
    body = rf"""
$ErrorActionPreference = 'Stop'
Import-Module '{psd1}' -Force -DisableNameChecking
& (Get-Module BobBridge) {{
  $work = [pscustomobject]@{{ X = 0; Y = 0; Width = 1920; Height = 1080 }}
  $cursor = [pscustomobject]@{{ X = 400; Y = 400 }}
  # Left empty / missing X - Width and Height present (UiDiag: iconRect=,-, w=32 h=48).
  $bad = [pscustomobject]@{{ Left = ''; Top = ''; Width = 32; Height = 48 }}
  $conv = ConvertTo-BobTrayRect $bad
  Write-Output ('convNull=' + ($null -eq $conv))
  $p = Get-BobTrayTipPlacement -TipWidth 420 -TipHeight 121 `
    -IconRect $bad -Cursor $cursor -WorkArea $work -AlreadyVisible $false
  Write-Output ('src=' + $p.source)
  # Hashtable with empty Left string (same failure mode).
  $bad2 = @{{ Left = ''; Y = 500; Width = 32; Height = 48 }}
  $conv2 = ConvertTo-BobTrayRect $bad2
  Write-Output ('conv2Null=' + ($null -eq $conv2))
  $p2 = Get-BobTrayTipPlacement -TipWidth 420 -TipHeight 121 `
    -IconRect $bad2 -Cursor $cursor -WorkArea $work -AlreadyVisible $false
  Write-Output ('src2=' + $p2.source)
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
    assert r.returncode == 0, r.stderr + r.stdout
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert any(ln == "convNull=True" for ln in lines), lines
    assert any(ln.startswith("src=") and "icon" not in ln.split("=", 1)[-1] for ln in lines), lines
    assert any(ln == "conv2Null=True" for ln in lines), lines
    assert any(ln.startswith("src2=") and "icon" not in ln.split("=", 1)[-1] for ln in lines), lines
