"""FR #6270: service/SYSTEM weekly acquisition must read the signed-in user profile.

Observed: ear/service context used the system profile (no Grok login), posted
stale carried weekly, diag home_role=service acquisition=system-profile-skipped.
Admin interactive profile had a live unified.jsonl reading.

Offline fixtures use 61 / 19 (never the live 82 / 74 / 43 set from #6267).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
DOCS = ROOT / "docs" / "bob-ear.md"
BOBREPORT = ROOT.parent / "common" / "scripts" / "bobreport.py"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _billing_line(period_end: datetime, used_pct: float) -> str:
    ev = {
        "ts": _iso(period_end - timedelta(hours=2)),
        "src": "shell",
        "ver": "1.0.40",
        "lvl": "info",
        "msg": "billing: fetched credits config",
        "ctx": {
            "config": {
                "creditUsagePercent": used_pct,
                "currentPeriod": {
                    "type": "USAGE_PERIOD_TYPE_WEEKLY",
                    "start": _iso(period_end - timedelta(days=7)),
                    "end": _iso(period_end),
                },
            }
        },
    }
    return json.dumps(ev)


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6270_source_pins_profile_resolve_and_no_stale_carry():
    h = _txt(HOVER)
    assert "FR #6270" in h
    assert "function Resolve-BobGrokWeeklyUserHome" in h
    assert "system-profile-skipped" in h
    assert "interactive-profile" in h
    irc = _txt(IRC)
    assert "FR #6270" in irc
    assert "never re-post a carried Prev.weekly" in irc
    br = _txt(BOBREPORT)
    assert "FR #6270" in br
    assert "interactive-profile" in br
    assert "_interactive_grok_user_home" in br
    assert DOCS.is_file()
    d = _txt(DOCS)
    assert "FR #6270" in d


@needs_ps
def test_fr6270_service_context_reads_interactive_profile_log_61(tmp_path: Path):
    """SYSTEM-like home has no log; interactive user home has 61% remaining."""
    sys_home = tmp_path / "SystemProfile"
    user_home = tmp_path / "Users" / "FleetAdmin"
    log_dir = user_home / ".grok" / "logs"
    log_dir.mkdir(parents=True)
    end = datetime.now(timezone.utc) + timedelta(days=3)
    # used 39 => remaining 61 (not 82/74/43)
    (log_dir / "unified.jsonl").write_text(
        _billing_line(end, 39.0) + "\n", encoding="utf-8"
    )
    script = tmp_path / "fr6270-acq.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $env:USERPROFILE = '{sys_home}'
            $env:BOB_GROK_WEEKLY_USER_HOME = '{user_home}'
            $env:BOB_WEEKLY_FORCE_SYSTEM_PROFILE = '1'
            . '{HOVER}'
            $acq = Resolve-BobGrokWeeklyUserHome
            if ($acq.home_role -ne 'service') {{ throw ("role={{0}}" -f $acq.home_role) }}
            if ($acq.acquisition -ne 'interactive-profile') {{ throw ("acq={{0}}" -f $acq.acquisition) }}
            $w = Get-BobWeeklyRemaining
            if ($null -eq $w -or $w.remaining_pct -ne 61) {{ throw ("pct={{0}}" -f $w.remaining_pct) }}
            if (-not $w.fetched_at) {{ throw 'missing fetched_at' }}
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
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "ok" in (r.stdout or "")


@needs_ps
def test_fr6270_system_profile_skipped_does_not_invent_or_carry_19(tmp_path: Path):
    """No interactive log => acquisition system-profile-skipped; remaining unknown (not 19)."""
    sys_home = tmp_path / "SystemProfile"
    sys_home.mkdir(parents=True)
    script = tmp_path / "fr6270-skip.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $env:USERPROFILE = '{sys_home}'
            $env:BOB_WEEKLY_FORCE_SYSTEM_PROFILE = '1'
            Remove-Item Env:BOB_GROK_WEEKLY_USER_HOME -ErrorAction SilentlyContinue
            Remove-Item Env:BOB_WEEKLY_LOG -ErrorAction SilentlyContinue
            . '{HOVER}'
            $acq = Resolve-BobGrokWeeklyUserHome
            if ($acq.acquisition -ne 'system-profile-skipped') {{ throw ("acq={{0}}" -f $acq.acquisition) }}
            $w = Get-BobWeeklyRemaining
            if ($null -ne $w -and $null -ne $w.remaining_pct) {{ throw ("invented={{0}}" -f $w.remaining_pct) }}
            Import-Module '{ROOT / "tray" / "src" / "BobBridge.psd1"}' -Force -DisableNameChecking
            & (Get-Module BobBridge) {{
                $doc = [pscustomobject]@{{ id = 'marchhare'; weekly = $null; weekly_known = $false }}
                $prev = [pscustomobject]@{{ weekly = 19; period_end = '2099-01-01T00:00:00Z' }}
                $ent = [pscustomobject]@{{ weekly_known = $false }}
                $merged = Merge-BobIrcDigestPeerWithPrevious -Ent $ent -Doc $doc -Prev $prev
                if ($null -ne $merged.weekly -and [string]$merged.weekly -ne '') {{
                    throw ("carried={{0}}" -f $merged.weekly)
                }}
            }}
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
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "ok" in (r.stdout or "")
