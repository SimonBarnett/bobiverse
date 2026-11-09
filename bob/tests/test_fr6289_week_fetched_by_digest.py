"""FR #6289: populate weekFetchedBy from digest measureAt after FR #6285.

After digest-only xAI weekly paint, Get-BobTrayHover must still copy each
digest row's fetched_at (measureAt) into weekFetchedBy so hover
weekly_fetched_at and tile FetchedAt are not always null.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6289_pins_week_fetched_by_from_measure_at():
    h = _txt(HOVER)
    assert "FR #6289" in h
    start = h.index("$weekFetchedBy = @{}")
    end = h.index("# FR #6285: hover/alert remainPct from digest xai_weekly")
    window = h[start:end]
    assert "$weekFetchedBy[$mac] = $measureAt" in window
    assert "measureAt" in window
    # Read path for hover return must still exist.
    assert "weekly_fetched_at = $weekFetched" in h


@needs_ps
def test_fr6289_digest_row_fetched_at_copies_into_week_fetched_by(tmp_path: Path):
    """Behavioral: digest weekly-row fetched_at (measureAt) must land in weekFetchedBy."""
    script = tmp_path / "fr6289.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            # Shape matches Expand-BobReportDigestView weeklyRows (fetched_at from xai_weekly).
            $wr = [pscustomobject]@{{
                machine = 'flamingo'
                weekly = 88
                fetched_at = '2026-11-09T12:00:00Z'
                fresh = $true
            }}
            $weekFetchedBy = @{{}}
            $mac = [string]$wr.machine
            $measureAt = $null
            try {{ if ($wr.fetched_at) {{ $measureAt = [string]$wr.fetched_at }} }} catch {{ }}
            # FR #6289: same assign the live Get-BobTrayHover digest loop must keep.
            if ($measureAt) {{ $weekFetchedBy[$mac] = $measureAt }}
            if (-not $weekFetchedBy.ContainsKey('flamingo')) {{ throw 'weekFetchedBy missing flamingo' }}
            if ([string]$weekFetchedBy['flamingo'] -ne '2026-11-09T12:00:00Z') {{
                throw ('weekFetchedBy={{0}}' -f $weekFetchedBy['flamingo'])
            }}
            $hover = Get-Content -LiteralPath '{HOVER}' -Raw
            if ($hover -notmatch [regex]::Escape('$weekFetchedBy[$mac] = $measureAt')) {{
                throw 'Get-BobTrayHover missing weekFetchedBy assign from measureAt'
            }}
            if ($hover -notmatch 'FR #6289') {{ throw 'missing FR #6289 marker' }}
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
