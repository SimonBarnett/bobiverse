"""FR #7498: digest Grok/xAI remaining comes only from machines.*.xai_weekly.

pcent.grok-chat / cursor_pools / bare weekly are not Grok remaining meters.
Format forces stale when age_s > 120 or fetched_at older than 2 minutes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
WATCHER = ROOT / "tray" / "src" / "Private" / "Test-BobWatcher.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _extract_fn(src: str, name: str) -> str:
    """Extract `function Name { ... }` including nested braces."""
    m = re.search(rf"(?ms)^function\s+{re.escape(name)}\b\s*\{{", src)
    if not m:
        raise AssertionError(f"missing function {name}")
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[m.start() : j + 1]
    raise AssertionError(f"unclosed function {name}")


def test_fr7498_watch_resolve_digest_fill_uses_xai_weekly_not_pcent():
    w = _txt(WATCH)
    assert "function Get-BobTrayMachineXaiWeekly" in w
    assert "function Resolve-BobTrayGrokFuelAtStart" in w
    resolve = _extract_fn(w, "Resolve-BobTrayGrokFuelAtStart")
    helper = _extract_fn(w, "Get-BobTrayMachineXaiWeekly")
    # Digest fill path must call xai_weekly helper, never Sand pcent reader.
    assert "Get-BobTrayMachineXaiWeekly" in resolve
    assert "Get-BobTrayMachineGrokChatPcent" not in resolve
    # Helper body reads xai_weekly only (not cursor_pools / bare weekly remaining).
    assert "xai_weekly" in helper
    assert "remaining_pct" in helper
    assert "fetched_at" in helper
    helper_live = re.sub(r"(?s)<#.*?#>", "", helper)
    helper_live = re.sub(r"(?m)^\s*#.*$", "", helper_live)
    assert "cursor_pools" not in helper_live
    # Old Sand reader must not remain as a live remaining path.
    assert "function Get-BobTrayMachineGrokChatPcent" not in w
    # Live code (comments stripped) must not read pcent.grok-chat.
    live = re.sub(r"(?s)<#.*?#>", "", resolve + "\n" + helper)
    live = re.sub(r"(?m)^\s*#.*$", "", live)
    assert "pcent.'grok-chat'" not in live
    assert 'pcent."grok-chat"' not in live
    assert "pcent['grok-chat']" not in live
    assert re.search(r"\$\w*\.pcent\b", live) is None


def test_fr7498_format_forces_stale_over_two_minutes():
    h = _txt(HOVER)
    fmt = _extract_fn(h, "Format-BobTrayXaiWeeklyRow")
    assert "FR #7498" in fmt or "120" in fmt
    assert "fuel_stale" in fmt
    # age_s / fetched_at age must force fresh=false.
    assert "120" in fmt
    sel = _extract_fn(h, "Select-BobTrayXaiWeeklyFromDigestNode")
    assert "xai_weekly" in sel
    assert "node.weekly" in sel.lower() or "Ignore node.weekly" in sel or "ignore" in sel.lower()


@needs_ps
def test_fr7498_format_prefers_xai_weekly_55_over_pcent_74(tmp_path: Path):
    script = tmp_path / "fr7498_fmt.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            function Resolve-BobiverseMachineId {{ param($Id) return ([string]$Id).ToLowerInvariant() }}
            function ConvertTo-BobTrayIntOrNull {{
                param($Value)
                if ($null -eq $Value -or [string]$Value -eq '') {{ return $null }}
                try {{ return [int]$Value }} catch {{ return $null }}
            }}
            . '{HOVER}'
            . '{WATCHER}'
            $node = [pscustomobject]@{{
                weekly = 74
                pcent = [pscustomobject]@{{ 'grok-chat' = 74; 'cursor-models' = 74 }}
                cursor_pools = @(
                    [pscustomobject]@{{ group_id = 'grok-chat'; remaining_pct = 74 }}
                )
                xai_weekly = [pscustomobject]@{{
                    remaining_pct = 55
                    account = 'mh-xai'
                    period_end = '2026-11-21T12:00:00Z'
                    fetched_at = ([datetime]::UtcNow.AddSeconds(-30).ToString('o'))
                    fresh = $true
                    age_s = 30
                    error = $null
                }}
            }}
            $sel = Select-BobTrayXaiWeeklyFromDigestNode -Node $node
            if ($null -eq $sel) {{ throw 'select returned null' }}
            if ([int]$sel.remaining_pct -ne 55) {{ throw ('select pct={{0}}' -f $sel.remaining_pct) }}
            $row = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly $sel
            if ([int]$row.remaining_pct -ne 55) {{ throw ('format pct={{0}}' -f $row.remaining_pct) }}
            if ($row.fuel_stale) {{ throw 'fresh xai_weekly must not be stale' }}
            if ($row.bar_pct -ne 55) {{ throw 'fresh bar_pct' }}
            if ($row.heading -match '74') {{ throw ('heading leaked pcent 74: {{0}}' -f $row.heading) }}
            if ($row.source -ne 'digest-xai_weekly') {{ throw ('source={{0}}' -f $row.source) }}

            $view = Expand-BobReportDigestView -Digest ([pscustomobject]@{{
                machines = [pscustomobject]@{{ marchhare = $node }}
            }})
            $wr = @($view.weeklyRows | Where-Object {{ $_.machine -eq 'marchhare' }})[0]
            if ([int]$wr.weekly -ne 55) {{ throw ('expand weekly={{0}}' -f $wr.weekly) }}
            if ([int]$wr.xai_weekly.remaining_pct -ne 55) {{ throw 'expand xai remaining' }}

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
def test_fr7498_format_stale_when_fetched_at_over_two_minutes(tmp_path: Path):
    script = tmp_path / "fr7498_stale.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . '{HOVER}'
            . '{WATCHER}'
            $old = [datetime]::UtcNow.AddMinutes(-5).ToString('o')
            $row = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 55
                account = 'mh-xai'
                period_end = '2026-11-21T12:00:00Z'
                fetched_at = $old
                fresh = $true
                age_s = 300
                error = $null
            }})
            if (-not $row.fuel_stale) {{ throw 'age_s>120 must force fuel_stale' }}
            if ($null -ne $row.bar_pct) {{ throw 'stale bar_pct must be null' }}
            if ([int]$row.remaining_pct -ne 55) {{ throw 'stale keeps last remaining_pct' }}
            if ($row.heading -notmatch '\\[stale\\]') {{ throw ('stale mark missing: {{0}}' -f $row.heading) }}

            # fetched_at alone (no age_s) older than 2 min also forces stale even if fresh=true.
            $row2 = Format-BobTrayXaiWeeklyRow -MachineId 'flamingo' -XaiWeekly ([pscustomobject]@{{
                remaining_pct = 55
                fetched_at = $old
                fresh = $true
            }})
            if (-not $row2.fuel_stale) {{ throw 'old fetched_at must force stale' }}
            if ($null -ne $row2.bar_pct) {{ throw 'fetched_at-stale bar null' }}

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
def test_fr7498_resolve_digest_fill_returns_xai_weekly_55(tmp_path: Path):
    """Resolve-BobTrayGrokFuelAtStart digest fill uses xai_weekly 55, not pcent 74."""
    w = _txt(WATCH)
    helper = _extract_fn(w, "Get-BobTrayMachineXaiWeekly")
    resolve = _extract_fn(w, "Resolve-BobTrayGrokFuelAtStart")
    script = tmp_path / "fr7498_resolve.ps1"
    # Isolated: stub local weekly/fuel readers so digest fill runs.
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            function Resolve-BobiverseMachineId {{ param($Id) return ([string]$Id).ToLowerInvariant() }}
            function Get-BobTrayFuelLocalMachineId {{ return 'marchhare' }}
            function Get-BobTrayDigestReportUrl {{ return 'https://example.test/bob/v1/report' }}
            function Get-BobTrayGrokFuelRemaining {{ return $null }}
            function Get-BobWeeklyRemaining {{ return $null }}
            function Get-BobGrokAuthSnapshot {{ return $null }}
            function Get-BobGrokAvailability {{ return $null }}
            function Write-TrayLog {{ param($Message) }}
            {helper}
            {resolve}
            $digest = [pscustomobject]@{{
                machines = [pscustomobject]@{{
                    marchhare = [pscustomobject]@{{
                        weekly = 74
                        pcent = [pscustomobject]@{{ 'grok-chat' = 74 }}
                        cursor_pools = @([pscustomobject]@{{ group_id = 'grok-chat'; remaining_pct = 74 }})
                        xai_weekly = [pscustomobject]@{{
                            remaining_pct = 55
                            account = 'mh-xai'
                            period_end = '2026-11-21T12:00:00Z'
                            fetched_at = ([datetime]::UtcNow.AddSeconds(-20).ToString('o'))
                            fresh = $true
                        }}
                    }}
                }}
            }}
            $xw = Get-BobTrayMachineXaiWeekly -MachineId 'marchhare' -Digest $digest
            if ($null -eq $xw) {{ throw 'xai weekly null' }}
            if ([int]$xw.remaining_pct -ne 55) {{ throw ('helper pct={{0}}' -f $xw.remaining_pct) }}
            $d = Resolve-BobTrayGrokFuelAtStart -MachineId 'marchhare' -Digest $digest
            if ([int]$d.remaining -ne 55) {{ throw ('resolve remaining={{0}}' -f $d.remaining) }}
            if ($d.action -ne 'start-pool') {{ throw ('action={{0}}' -f $d.action) }}
            $o = [ordered]@{{ remaining = [int]$d.remaining; account = [string]$xw.account }}
            $o | ConvertTo-Json -Compress
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
    data = json.loads((r.stdout or "").strip().splitlines()[-1])
    assert data["remaining"] == 55
    assert data["account"] == "mh-xai"


def test_fr7498_watch_helper_grep_clean_of_pcent_remaining_read():
    """Hostile: Watch Grok digest helper must not read pcent/cursor_pools/bare weekly."""
    w = _txt(WATCH)
    helper = _extract_fn(w, "Get-BobTrayMachineXaiWeekly")
    resolve = _extract_fn(w, "Resolve-BobTrayGrokFuelAtStart")
    combined = helper + "\n" + resolve
    # Allow comment/help text that says never use Sand leftovers; forbid property reads.
    code = re.sub(r"(?s)<#.*?#>", "", combined)
    code = re.sub(r"(?m)^\s*#.*$", "", code)
    assert re.search(r"\bpcent\b", code) is None, "pcent still referenced in live code"
    assert "cursor_pools" not in code
    # Bare node.weekly remaining fill must not appear in helper/resolve.
    assert re.search(r"\$ent\.weekly\b", code) is None
    assert re.search(r"\$node\.weekly\b", code) is None
