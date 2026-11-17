"""FR #8049: tray never paints raw HTTP 503; last % stays; [stale] only when due."""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr8049_pins_no_raw_http_in_format_helper():
    h = _txt(HOVER)
    assert "FR #8049" in h
    assert "Test-BobTrayHttpPoolError" in h


def test_fr8049_docs_standing_rule():
    d = _txt(DOCS)
    assert "FR #8049" in d
    assert "[stale]" in d


@needs_ps
def test_fr8049_single_503_keeps_row_without_status(tmp_path: Path):
    script = tmp_path / "fr8049_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $live = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 97
                period_end = '2026-11-22T19:28:11Z'
                fresh = $true
                error = 'provider-http-503'
                age_s = 20
                account = 'social@clubmadeira.uk'
                fetched_at = '2026-11-17T15:14:00Z'
            }}) -AsPublished
            if ($live.remaining_pct -ne 97) {{ throw 'must keep last remaining_pct' }}
            if ($live.fuel_stale) {{ throw 'single transient must not force stale while fresh=true' }}
            if ($live.heading -notmatch '97% left') {{ throw ('pct missing={{0}}' -f $live.heading) }}
            if ($live.heading -match '503') {{ throw ('raw 503 must not appear={{0}}' -f $live.heading) }}
            if ($live.heading -match 'provider-http') {{ throw ('provider-http must not appear={{0}}' -f $live.heading) }}
            if ($live.heading -match '\\[stale\\]') {{ throw ('must not show stale yet={{0}}' -f $live.heading) }}
            if ($live.error -ne 'provider-http-503') {{ throw 'error field stays class for diagnostics' }}

            $stale = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 97
                period_end = '2026-11-22T19:28:11Z'
                fresh = $false
                error = 'provider-http-503'
                age_s = 180
                account = 'social@clubmadeira.uk'
                fetched_at = '2026-11-17T15:10:00Z'
            }}) -AsPublished
            if ($stale.remaining_pct -ne 97) {{ throw 'stale must keep last %' }}
            if (-not $stale.fuel_stale) {{ throw 'must be stale' }}
            if ($stale.heading -notmatch '97% left') {{ throw ('pct missing={{0}}' -f $stale.heading) }}
            if ($stale.heading -notmatch '\\[stale\\]') {{ throw ('stale mark missing={{0}}' -f $stale.heading) }}
            if ($stale.heading -match '503') {{ throw ('raw 503 must not appear when stale={{0}}' -f $stale.heading) }}
            if ($stale.heading -match 'provider-http') {{ throw ('provider-http must not appear when stale={{0}}' -f $stale.heading) }}

            $bare = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = $null
                fresh = $false
                error = '503'
                age_s = 200
            }}) -AsPublished
            if ($bare.heading -match 'unknown\\s+\\(503\\)') {{ throw ('unknown (503) painted={{0}}' -f $bare.heading) }}
            if ($bare.heading -match '(^|\\s)503(\\s|$)') {{ throw ('bare 503 token={{0}}' -f $bare.heading) }}

            Write-Output 'ok'
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "ok" in (r.stdout or "")
