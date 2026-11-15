"""FR #7522: tray Copilot/OpenCode/xAI 0% + future reset paints no [stale]."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


def test_fr7522_source_pins_exhausted_until_reset():
    t = HOVER.read_text(encoding="utf-8-sig")
    assert "FR #7522" in t
    assert "Test-BobPoolExhaustedUntilReset" in t
    assert "RemainingPct" in t[t.find("function Get-BobPoolReadingFreshness") :][
        :1200
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7522_copilot_zero_future_reset_no_stale_token():
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-15T15:30:00Z'
$pool = [pscustomobject]@{{
  state='exhausted'; remaining=0; fetched_at='2026-11-15T10:00:00Z'
  reset_at='2026-12-01T00:00:00Z'
}}
$line = Format-BobCopilotPoolLine -Pool $pool -Now $now
Write-Output ('LINE=' + $line)
$fr = Get-BobCopilotFreshness -Pool $pool -Now $now
Write-Output ('STATE=' + $fr.state)
$pool2 = [pscustomobject]@{{
  state='ok'; remaining=0; fetched_at='2026-11-15T10:00:00Z'
  reset_at='2026-11-01T00:00:00Z'
}}
$line2 = Format-BobCopilotPoolLine -Pool $pool2 -Now $now
Write-Output ('PAST=' + $line2)
$pool3 = [pscustomobject]@{{
  state='ok'; remaining=50; fetched_at='2026-11-15T10:00:00Z'
  reset_at='2026-12-01T00:00:00Z'
}}
$line3 = Format-BobCopilotPoolLine -Pool $pool3 -Now $now
Write-Output ('FIFTY=' + $line3)
$pool4 = [pscustomobject]@{{
  state='ok'; remaining=50; fetched_at='2026-11-15T15:29:00Z'
  reset_at='2026-12-01T00:00:00Z'
}}
$line4 = Format-BobCopilotPoolLine -Pool $pool4 -Now $now
Write-Output ('FRESH=' + $line4)
"""
    out = {
        ln.split("=", 1)[0]: ln.split("=", 1)[1]
        for ln in _ps(script).splitlines()
        if "=" in ln
    }
    assert out.get("STATE") == "fresh"
    assert "[stale]" not in (out.get("LINE") or "")
    assert "0% left" in (out.get("LINE") or "")
    assert "[stale]" in (out.get("PAST") or "")
    assert "[stale]" in (out.get("FIFTY") or "")
    assert "[stale]" not in (out.get("FRESH") or "")
    assert "50% left" in (out.get("FRESH") or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7522_opencode_zero_future_reset_shows_pct():
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-15T15:30:00Z'
$rec = [pscustomobject]@{{
  status='exhausted'; remaining_pct=0; fetched_at='2026-11-15T10:00:00Z'
  period_end='2026-12-01T00:00:00Z'; reset_label='15d 10h'
}}
$line = Format-BobOpencodeWindowLine -WindowId week -Record $rec -Now $now
Write-Output ('LINE=' + $line)
"""
    out = _ps(script)
    assert "[stale]" not in out
    assert "0% left" in out
