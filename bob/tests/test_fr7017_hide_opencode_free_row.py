"""FR #7017: tray must never show the OpenCode free row on any machine.

Free models have no measurable quota. Hide free row/bar/summary bit for free=
100, null, 0, and stale. Keep Go rolling/weekly/monthly window lines unchanged.
Fuel detection (opencode_fuel free_model_ids) is out of scope.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
COMMON = ROOT.parent / "common" / "scripts"
sys.path.insert(0, str(COMMON))
import opencode_fuel as of  # noqa: E402

GO_LINES = ("go rolling", "go weekly", "go monthly")


def _ps_format(free, stale: bool = False) -> dict:
    stale_sw = " -Stale" if stale else ""
    free_lit = "$null" if free is None else str(int(free))
    script = f"""
. '{HOVER}'
$wins = [pscustomobject]@{{
  rolling = [pscustomobject]@{{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }}
  week    = [pscustomobject]@{{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }}
  month   = [pscustomobject]@{{ status = 'unknown'; used_pct = $null; remaining_pct = $null; reset_label = $null }}
}}
$pack = Format-BobOpencodeWindowLines -FreePct {free_lit} -Windows $wins{stale_sw}
$line = Format-BobOpencodePoolLine -FreePct {free_lit} -GoPct $null -Windows $wins{stale_sw}
$o = [ordered]@{{
  summary = [string]$pack.summary
  free_heading = $(if ($null -eq $pack.free_heading) {{ $null }} else {{ [string]$pack.free_heading }})
  window_lines = @($pack.window_lines)
  bar_ids = @($pack.bars | ForEach-Object {{ [string]$_.id }})
  pool_line = [string]$line
}}
$o | ConvertTo-Json -Compress
"""
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={k: v for k, v in os.environ.items()},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("free", [100, None, 0])
def test_fr7017_ps_hides_free_for_values(free):
    pack = _ps_format(free, stale=False)
    assert "free" not in pack["summary"].lower() or pack["summary"].lower().startswith(
        "opencode  go"
    )
    assert "OpenCode  free" not in pack["summary"]
    assert not pack.get("free_heading")
    assert "free" not in [str(x).lower() for x in pack.get("bar_ids") or []]
    assert "OpenCode  free" not in pack["pool_line"]
    joined = "\n".join(pack["window_lines"])
    for needle in GO_LINES:
        assert needle in joined, (needle, pack["window_lines"])


def test_fr7017_ps_hides_free_when_stale():
    pack = _ps_format(50, stale=True)
    assert "OpenCode  free" not in pack["summary"]
    assert "[stale]" in pack["summary"]
    assert "free" not in [str(x).lower() for x in pack["bar_ids"]]
    joined = "\n".join(pack["window_lines"])
    for needle in GO_LINES:
        assert needle in joined


@pytest.mark.parametrize("free", [100, None, 0])
def test_fr7017_python_paint_hides_free(free):
    paint = of.format_opencode_paint_lines(free, None)
    assert "OpenCode  free" not in paint["summary"]
    assert paint["free_heading"] is None
    assert paint["summary"].startswith("OpenCode  go")
    bars = of.opencode_pool_bars(free, None)
    assert "free" not in [b["id"] for b in bars]
    assert [b["id"] for b in bars] == ["rolling", "week", "month"]
    joined = "\n".join(paint["window_lines"])
    for needle in GO_LINES:
        assert needle in joined


def test_fr7017_python_paint_hides_free_when_stale():
    paint = of.format_opencode_paint_lines(40, None, stale=True)
    assert "OpenCode  free" not in paint["summary"]
    assert "[stale]" in paint["summary"]
    bars = of.opencode_pool_bars(40, None, stale=True)
    assert "free" not in [b["id"] for b in bars]
