"""FR #7242: tray unknown+reason when a pool has no real remaining (not 0%)."""
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


def test_fr7242_pins():
    t = HOVER.read_text(encoding="utf-8-sig")
    assert "FR #7242" in t
    assert "Test-BobTrayPoolHasRealRemaining" in t
    d = DOCS.read_text(encoding="utf-8")
    assert "FR #7242" in d


@needs_ps
def test_fr7242_skip_error_zero_is_unknown(tmp_path: Path) -> None:
    script = tmp_path / "fr7242.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $skip = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 0
                weekly_known = $false
                fresh = $false
                error = 'system-profile-skipped'
                age_s = 100800
            }})
            if ($skip.heading -match '0% left') {{ throw ('skip painted zero={{0}}' -f $skip.heading) }}
            if ($skip.heading -notmatch 'unknown') {{ throw ('need unknown={{0}}' -f $skip.heading) }}
            if ($skip.heading -notmatch 'system-profile-skipped') {{ throw ('need reason={{0}}' -f $skip.heading) }}
            if ($null -ne $skip.bar_pct) {{ throw 'unknown bar must be null' }}
            if ($null -ne $skip.remaining_pct) {{ throw 'remaining must be null' }}

            $realZero = Format-BobTrayXaiWeeklyRow -MachineId 'ionos' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 0
                weekly_known = $true
                fresh = $true
                error = $null
            }})
            if ($realZero.heading -notmatch '0% left') {{ throw ('real zero={{0}}' -f $realZero.heading) }}
            if ($realZero.bar_pct -ne 0) {{ throw 'real zero bar' }}

            $staleGood = Format-BobTrayXaiWeeklyRow -MachineId 'redqueen' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 41
                weekly_known = $true
                fresh = $false
                error = 'grok-login-expired'
                age_s = 3600
            }})
            if ($staleGood.heading -notmatch '41% left') {{ throw ('keep last-good={{0}}' -f $staleGood.heading) }}

            $cop = Format-BobCopilotPoolLine -Pool ([pscustomobject]@{{
                state='no_token'; remaining=0; last_error='no_token'
                fetched_at='2026-11-14T14:36:00Z'
            }})
            if ($cop -match '0% left') {{ throw ('copilot zero={{0}}' -f $cop) }}
            if ($cop -notmatch 'unknown') {{ throw ('copilot unknown={{0}}' -f $cop) }}
            if ($cop -notmatch 'no_token') {{ throw ('copilot reason={{0}}' -f $cop) }}
            $bar = Get-BobCopilotMeterBarPct -Pool ([pscustomobject]@{{ state='no_token'; remaining=0; last_error='no_token' }})
            if ($null -ne $bar) {{ throw 'copilot unknown bar' }}

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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in (r.stdout or "")
