"""FR #6285: TipForm/Status xAI weekly rows come only from digest xai_weekly.

No local unified.jsonl / Get-BobWeeklyRemaining for display. Stale marks + error
from the meter. Null meter => clear 'no reading'. Heading is 'xAI weekly' only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6285_pins_digest_only_helpers_and_heading():
    h = _txt(HOVER)
    assert "FR #6285" in h
    assert "function Format-BobTrayXaiWeeklyRow" in h
    assert "function Select-BobTrayXaiWeeklyFromDigestNode" in h
    # Display must not prefer local weekly over digest xai_weekly for own machine.
    assert "localWeeklyLocked" in h  # still may exist for non-display
    # But the xAI paint path must cite FR #6285 digest-only.
    assert "digest xai_weekly" in h.lower() or "xai_weekly only" in h.lower() or "FR #6285" in h

    w = _txt(WATCH)
    rebuild = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "xAI weekly" in rebuild
    assert "Cursor / xAI" not in rebuild
    assert "FR #6285" in rebuild
    assert "pool_heading" in rebuild
    assert "bar_pct" in rebuild

    st = _txt(STATUS_CS)
    render = st[st.index("public int Render") : st.index("protected override void OnPaint")]
    assert 'Section(g, y, "xAI weekly"' in render
    assert "Cursor / xAI" not in render

    dlg = _txt(DIALOGS)
    assert "pool_heading" in dlg
    assert "bar_pct" in dlg

    d = _txt(DOCS)
    assert "FR #6285" in d


@needs_ps
def test_fr6285_format_fresh_stale_null_account(tmp_path: Path):
    script = tmp_path / "fr6285_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $fresh = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 14
                period_end = '2026-11-14T12:58:59Z'
                fresh = $true
                account = 'bob-marchhare'
                error = $null
                age_s = 10
            }})
            if ($fresh.remaining_pct -ne 14) {{ throw ('fresh pct={{0}}' -f $fresh.remaining_pct) }}
            if ($fresh.fuel_stale) {{ throw 'fresh must not be stale' }}
            if ($fresh.heading -notmatch '14% left') {{ throw ('fresh heading={{0}}' -f $fresh.heading) }}
            if ($fresh.heading -notmatch 'bob-marchhare') {{ throw 'account missing' }}
            if ($fresh.heading -match '\\[stale') {{ throw 'fresh must not show stale mark' }}

            $stale = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 14
                period_end = '2026-11-14T12:58:59Z'
                fresh = $false
                error = 'auth-file-unreadable'
                age_s = 819
                account = $null
            }})
            if ($stale.remaining_pct -ne 14) {{ throw 'stale keeps last remaining_pct' }}
            if (-not $stale.fuel_stale) {{ throw 'stale flag' }}
            if ($stale.heading -notmatch '14% left') {{ throw ('stale heading pct={{0}}' -f $stale.heading) }}
            if ($stale.heading -notmatch 'stale') {{ throw ('stale mark missing={{0}}' -f $stale.heading) }}
            if ($stale.heading -notmatch 'auth-file-unreadable') {{ throw 'error missing' }}
            if ($null -ne $stale.bar_pct) {{ throw 'stale bar must be empty (value only with mark in heading)' }}

            $none = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly $null
            if ($null -ne $none.remaining_pct) {{ throw 'null meter must not invent pct' }}
            if ($none.heading -notmatch 'no reading') {{ throw ('null heading={{0}}' -f $none.heading) }}
            if ($null -ne $none.bar_pct) {{ throw 'null meter empty bar' }}

            # Digest node with weekly=88 but xai_weekly null must not use weekly.
            $sel = Select-BobTrayXaiWeeklyFromDigestNode -Node ([pscustomobject]@{{
                weekly = 88
                xai_weekly = $null
            }})
            if ($null -ne $sel) {{ throw 'null xai_weekly must win over weekly int' }}

            $sel2 = Select-BobTrayXaiWeeklyFromDigestNode -Node ([pscustomobject]@{{
                weekly = 99
                xai_weekly = [pscustomobject]@{{ remaining_pct = 14; fresh = $false; error = 'auth-file-unreadable'; age_s = 5 }}
            }})
            if ($sel2.remaining_pct -ne 14) {{ throw ('digest remaining must be 14 not 99 got={{0}}' -f $sel2.remaining_pct) }}

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


@needs_ps
def test_fr6285_display_path_does_not_call_local_weekly_reader(tmp_path: Path):
    """Source pin: Format-BobTrayXaiWeeklyRow / Select helpers never call Get-BobWeeklyRemaining."""
    h = _txt(HOVER)
    # Slice from Format-BobTrayXaiWeeklyRow through Select-BobTrayXaiWeeklyFromDigestNode end.
    start = h.index("function Format-BobTrayXaiWeeklyRow")
    mid = h.index("function Select-BobTrayXaiWeeklyFromDigestNode")
    # take a bounded window after Select
    end = h.index("\nfunction ", mid + 10)
    window = h[start:end]
    assert "Get-BobWeeklyRemaining" not in window
    assert "unified.jsonl" not in window
    assert "xai_weekly" in window
