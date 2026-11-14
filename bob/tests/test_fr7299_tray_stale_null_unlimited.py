"""FR #7299: tray null/missing fetched_at/unlimited/stale render (red [stale])."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7299_copilot_unlimited_never_zero():
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-14T18:00:00Z'
$pool = [pscustomobject]@{{
  state='ok'; remaining=$null; unlimited=$true; used=50; max_recorded_usage=50
  reset_at='2026-12-01T00:00:00Z'; fetched_at='2026-11-14T17:59:00Z'
}}
$line = Format-BobCopilotPoolLine -Pool $pool -Now $now
$bar = Get-BobCopilotMeterBarPct -Pool $pool -Now $now
$o = [ordered]@{{ line=$line; bar=$bar }}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert "unlimited" in data["line"].lower()
    assert "0%" not in data["line"]
    assert int(data["bar"]) == 100


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7299_copilot_stale_exact_token_no_older_than():
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-14T18:00:00Z'
$pool = [pscustomobject]@{{
  state='ok'; remaining=74; unlimited=$false
  reset_at='2026-12-01T00:00:00Z'; fetched_at='2026-11-14T17:56:00Z'
}}
$line = Format-BobCopilotPoolLine -Pool $pool -Now $now
$tok = Format-BobTrayStaleToken
$rgb = @(Get-BobTrayStaleForeColorArgb)
$o = [ordered]@{{ line=$line; tok=$tok; r=$rgb[0]; g=$rgb[1]; b=$rgb[2] }}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["tok"] == "[stale]"
    assert "[stale]" in data["line"]
    assert "older than" not in data["line"].lower()
    assert "74%" in data["line"]
    assert data["r"] == 248 and data["g"] == 81 and data["b"] == 73


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7299_null_remaining_unknown_not_number():
    script = f"""
. '{HOVER}'
$h = Format-BobTrayDigestPoolHeading -Label 'Grok Build' -RemainingPct $null -Reason 'login expired'
$h2 = Format-BobTrayDigestPoolHeading -Label 'Cursor / Grok chat' -RemainingPct $null -Stale
$o = [ordered]@{{ h=$h; h2=$h2 }}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert "unknown" in data["h"].lower()
    assert "%" not in data["h"].replace("100%", "")  # no percent number
    assert not any(ch.isdigit() for ch in data["h"].split("unknown")[0].split()[-1:]) or "Grok" in data["h"]
    # heading must not look like 'Grok Build 28%'
    assert "28%" not in data["h"]
    assert "[stale]" in data["h2"]
    assert "%" not in data["h2"]


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7299_missing_fetched_at_stale_with_last_value():
    script = f"""
. '{HOVER}'
$d = [pscustomobject]@{{
  machines = [pscustomobject]@{{}}
  fleet_pools = [pscustomobject]@{{
    cursor = [pscustomobject]@{{ remaining = 61; fetched_at = $null; fresh = $false }}
    copilot = [pscustomobject]@{{ remaining = 10; state = 'ok'; fetched_at = $null }}
    'opencode-go' = [pscustomobject]@{{ remaining = 40; fetched_at = $null }}
  }}
  copilot = [pscustomobject]@{{ remaining = 10; state = 'ok'; fetched_at = $null }}
}}
$rows = @(Get-BobTrayDigestPoolCatalog -Digest $d)
$cur = @($rows | Where-Object {{ $_.id -eq 'cursor' }})[0]
$o = [ordered]@{{ heading=$cur.heading; stale=[bool]$cur.stale; known=[bool]$cur.known; pct=$cur.remaining_pct }}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["stale"] is True
    assert "[stale]" in data["heading"]
    assert "61%" in data["heading"]
    assert "older than" not in data["heading"].lower()


def test_fr7299_watch_paints_stale_red():
    w = WATCH.read_text(encoding="utf-8-sig")
    assert "FR #7299" in w
    assert "FromArgb(248, 81, 73)" in w
    assert "[stale]" in w or "\\[stale\\]" in w
    assert "Stale is text, not red" not in w


def test_fr7299_hover_exports_stale_helpers():
    h = HOVER.read_text(encoding="utf-8-sig")
    assert "function Format-BobTrayStaleToken" in h
    assert "function Get-BobTrayStaleForeColorArgb" in h
    assert "if (-not $why) { $why = 'older than 2 min' }" not in h
    assert "$why = 'older than 2 min'" not in h
