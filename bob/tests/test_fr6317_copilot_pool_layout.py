"""FR #6317: Copilot paints like OpenCode rows (left 'Copilot - <text>' + bar).

Not section right-text, not red-for-stale. Known %, 0%, and unknown covered.
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
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6317_format_uses_hyphen_like_opencode():
    h = _txt(HOVER)
    fmt = h[h.index("function Format-BobCopilotPoolLine") : h.index("function Get-BobCopilotMeterBarPct")]
    assert "FR #6317" in fmt or "Copilot -" in fmt
    assert "'Copilot', 'unknown'" not in fmt or "Copilot - unknown" in fmt
    # No double-space join for the title/meter (OpenCode-style hyphen).
    assert " -join '  '" not in fmt or "Copilot -" in fmt


def test_fr6317_bar_pct_keeps_value_when_stale():
    """Stale must still yield remaining % for an empty/partial bar (not null)."""
    h = _txt(HOVER)
    bar = h[h.index("function Get-BobCopilotMeterBarPct") : h.index("function Test-BobPeriodExpired")]
    assert "FR #6317" in bar or "stale" in bar.lower()
    # Must not early-return null solely because freshness is stale.
    assert "if ($freshness.state -eq 'stale') { return $null }" not in bar


def test_fr6317_tipform_usage_row_not_section_right():
    w = _txt(WATCH)
    sec = w[w.index("FR #5172") : w.index("$indent = 18")]
    assert "FR #6317" in sec or "Add-BobTrayUsageRow" in sec
    assert "Format-BobCopilotPoolLine" in sec
    # Must not put meter on FuelFamilyRow RightText.
    assert "Add-BobTrayFuelFamilyRow -X 0 -Y $y -Family 'copilot' -Title 'Copilot'" in sec or (
        "Family 'copilot'" in sec and "RightText $copilot" not in sec
    )
    assert "RightText $copilotMeter" not in sec
    assert "RightText $copilotLine" not in sec
    # Usage row heading is the full Copilot - line (not stripped meter-only).
    assert "Add-BobTrayUsageRow" in sec
    assert "-Heading $copilotLine" in sec or "-Heading $copilotHeading" in sec


def test_fr6317_status_uses_usage_row_not_section_right():
    cs = _txt(STATUS_CS)
    render = cs[cs.index("string paintCopilot") : cs.index('Draw(g, "alert:')]
    assert "FR #6317" in render or "UsageRow" in render
    assert "copilotRight" not in render
    assert 'Section(g, y, copilotTitle, copilotRight' not in render
    assert "UsageRow" in render
    # Stale must not force Red title colour for the whole Copilot block.
    assert "StartsWith(\"Copilot  [stale\"" not in render or "Red" not in render.split("paintCopilot")[1][:400]


def test_fr6317_docs_pin():
    d = _txt(DOCS)
    assert "FR #6317" in d
    assert "Copilot -" in d


@needs_ps
def test_fr6317_format_known_zero_unknown(tmp_path: Path):
    script = tmp_path / "fr6317_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            $known = Format-BobCopilotPoolLine -Pool ([pscustomobject]@{{
                state='ok'; remaining=42; reset_at='2099-01-15T12:00:00Z'
                fetched_at='2099-01-01T12:00:00Z'
            }}) -Now ([datetime]'2099-01-01T12:00:00Z')
            if ($known -notmatch '^Copilot - 42% left') {{ throw ('known={{0}}' -f $known) }}
            if ($known -match 'Copilot  42') {{ throw 'double-space form must be gone' }}

            $zero = Format-BobCopilotPoolLine -Pool ([pscustomobject]@{{
                state='exhausted'; remaining=0; unlimited=$false
                fetched_at='2099-01-01T12:00:00Z'
            }}) -Now ([datetime]'2099-01-01T12:00:00Z')
            if ($zero -notmatch '^Copilot - 0% left') {{ throw ('zero={{0}}' -f $zero) }}

            $unk = Format-BobCopilotPoolLine -Pool $null
            if ($unk -ne 'Copilot - unknown') {{ throw ('unk={{0}}' -f $unk) }}

            $stalePool = [pscustomobject]@{{
                state='ok'; remaining=0; unlimited=$true; used=50; max_recorded_usage=50
                reset_at='2099-01-15T12:00:00Z'; fetched_at='2099-01-01T00:00:00Z'
            }}
            $staleLine = Format-BobCopilotPoolLine -Pool $stalePool -Now ([datetime]'2099-01-01T12:00:00Z')
            if ($staleLine -notmatch 'stale') {{ throw ('stale line={{0}}' -f $staleLine) }}
            if ($staleLine -match '% left') {{ throw ('stale must not look current={{0}}' -f $staleLine) }}
            $staleBar = Get-BobCopilotMeterBarPct -Pool $stalePool -Now ([datetime]'2099-01-01T12:00:00Z')
            if ($null -eq $staleBar) {{ throw 'stale bar must keep remaining pct (0), not null' }}
            if ([int]$staleBar -ne 0) {{ throw ('stale bar={{0}}' -f $staleBar) }}

            $unkBar = Get-BobCopilotMeterBarPct -Pool $null
            if ($null -ne $unkBar) {{ throw 'unknown bar must be null (neutral empty track)' }}

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
