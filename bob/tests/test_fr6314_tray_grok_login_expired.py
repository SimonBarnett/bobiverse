"""FR #6314: tray expands grok-login-expired into a clear re-sign-in message."""
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


def test_fr6314_pins_login_expired_message_in_format_helper():
    h = _txt(HOVER)
    assert "FR #6314" in h
    assert "grok-login-expired" in h
    assert "Grok login expired: run Grok on" in h
    assert "to sign in again" in h


def test_fr6314_docs_mention_expired_login():
    d = _txt(DOCS)
    assert "FR #6314" in d or "grok-login-expired" in d
    assert "Grok login expired" in d


@needs_ps
def test_fr6314_format_expands_login_expired(tmp_path: Path):
    script = tmp_path / "fr6314_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $expired = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 19
                period_end = '2026-11-15T12:00:00Z'
                fresh = $false
                error = 'grok-login-expired'
                age_s = 3900
                account = $null
                fetched_at = '2026-11-09T16:34:28Z'
            }})
            if ($expired.remaining_pct -ne 19) {{ throw 'must keep last remaining_pct' }}
            if (-not $expired.fuel_stale) {{ throw 'must be stale' }}
            if ($expired.heading -notmatch '19% left') {{ throw ('pct missing={{0}}' -f $expired.heading) }}
            if ($expired.heading -notmatch 'stale') {{ throw ('stale mark missing={{0}}' -f $expired.heading) }}
            if ($expired.heading -notmatch 'Grok login expired: run Grok on marchhare to sign in again') {{
                throw ('human message missing={{0}}' -f $expired.heading)
            }}
            if ($expired.heading -match 'provider-http-401') {{ throw 'bare 401 must not appear' }}
            if ($expired.heading -match 'grok-login-expired') {{ throw 'raw class must be expanded away from heading' }}
            if ($expired.error -ne 'grok-login-expired') {{ throw ('error field must stay class={{0}}' -f $expired.error) }}

            $five = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 14
                fresh = $false
                error = 'provider-http-500'
                age_s = 60
            }})
            if ($five.heading -notmatch 'provider-http-500') {{ throw ('500 must stay raw={{0}}' -f $five.heading) }}
            if ($five.heading -match 'Grok login expired') {{ throw '500 must not look like login expired' }}

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
