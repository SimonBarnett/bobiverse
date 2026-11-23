"""FR #8987 / BOB-HOVER-XAI: hover xAI weekly % matches Status; label xAI not SG."""
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


def test_fr8987_pins_xai_label_not_sg():
    h = _txt(HOVER)
    assert "FR #8987" in h
    assert "function Get-BobTrayHoverXaiPoolLabel" in h
    assert "function Format-BobTrayHoverXaiShort" in h
    assert "BOB-HOVER-XAI" in h
    # SuperGrok must never become SG on the hover path.
    assert "$tier = 'SG'" not in h
    assert "elseif ($t -match 'SuperGrok') { $tier = 'SG' }" not in h
    assert "Get-BobTrayHoverXaiPoolLabel" in h
    assert "Format-BobTrayHoverXaiShort" in h
    # Hover remainPct matches Status remaining_pct even when the meter is stale.
    assert "only when fresh" not in h
    assert "Same remaining_pct Status Format-BobTrayXaiWeeklyRow uses" in h


@needs_ps
def test_fr8987_hover_short_matches_status_xai_weekly_pct(tmp_path: Path):
    script = tmp_path / "fr8987_hover.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'

            foreach ($disp in @('SuperGrok', 'SuperGrok Heavy', 'xAI', '', 'SG')) {{
                $lab = Get-BobTrayHoverXaiPoolLabel -SubscriptionTierDisplay $disp
                if ($lab -ne 'xAI') {{ throw ("label for '{{0}}' got={{1}}" -f $disp, $lab) }}
                if ($lab -eq 'SG' -or $lab -match '(?i)^SG$') {{ throw 'SG must never be the pool tier' }}
            }}
            $prem = Get-BobTrayHoverXaiPoolLabel -SubscriptionTierDisplay 'Premium'
            if ($prem -ne 'P+') {{ throw ('Premium got={{0}}' -f $prem) }}

            $freshAt = [datetime]::UtcNow.AddSeconds(-10).ToString('yyyy-MM-ddTHH:mm:ssZ')
            $meter = [pscustomobject]@{{
                remaining_pct = 42
                period_end = '2026-12-01T00:00:00Z'
                fetched_at = $freshAt
                fresh = $true
                account = 'bob-flamingo'
                error = $null
                age_s = 10
            }}
            $status = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly $meter
            if ($status.remaining_pct -ne 42) {{ throw ('status pct={{0}}' -f $status.remaining_pct) }}

            $short = Format-BobTrayHoverXaiShort -TierLabel 'SuperGrok' -RemainingPct $status.remaining_pct -RunningCount 1
            if ($short -notmatch 'xAI') {{ throw ('short missing xAI: {{0}}' -f $short) }}
            if ($short -match '(?i)(?<![A-Za-z])SG(?![A-Za-z])') {{ throw ('short has SG: {{0}}' -f $short) }}
            if ($short -notmatch '42%') {{ throw ('short pct mismatch: {{0}}' -f $short) }}
            if ($short.Length -gt 63) {{ throw ('short too long {{0}}' -f $short.Length) }}

            $staleMeter = [pscustomobject]@{{
                remaining_pct = 14
                period_end = '2026-11-14T12:58:59Z'
                fresh = $false
                error = 'auth-file-unreadable'
                age_s = 819
            }}
            $staleStatus = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly $staleMeter
            if ($staleStatus.remaining_pct -ne 14) {{ throw 'stale status keeps remaining_pct' }}
            $staleShort = Format-BobTrayHoverXaiShort -TierLabel 'SuperGrok' -RemainingPct $staleStatus.remaining_pct -RunningCount 0
            if ($staleShort -notmatch '14%') {{ throw ('stale short must show Status pct: {{0}}' -f $staleShort) }}
            if ($staleShort -notmatch 'xAI') {{ throw ('stale short label: {{0}}' -f $staleShort) }}

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
    assert r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
    assert "ok" in (r.stdout or "")
