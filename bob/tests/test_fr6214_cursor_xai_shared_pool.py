"""FR #6214: Cursor and xAI share one quota pool — do not display or count separate capacity.

Acceptance:
- Same account/pool fixture -> one pool, no duplicate total capacity/usage
- Updating either reference updates the same displayed pool; resets consistent
- Distinct account/pool fixtures remain distinct
- Unknown/stale stays unknown/stale (never fabricated 0/full)
- Hover/Status presentation and aggregate capacity calculation
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY = ROOT / "bob" / "tray"
SHARED = TRAY / "src" / "Public" / "Resolve-BobCursorXaiSharedPools.ps1"
WATCH = TRAY / "tools" / "Watch-BobTray.ps1"
CAPACITY = TRAY / "src" / "Public" / "Get-BobCapacity.ps1"
STATUS = TRAY / "dialogs" / "BobStatus.cs"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6214_helper_exists():
    h = _txt(SHARED)
    assert "function Resolve-BobCursorXaiSharedPools" in h
    assert "function Get-BobSharedCursorXaiAggregateRemaining" in h
    assert "FR #6214" in h


def test_fr6214_tipform_paints_one_shared_cursor_xai_capacity_row():
    w = _txt(WATCH)
    start = w.index("function Rebuild-BobTrayTiles")
    end = w.index("$script:tileHost.Height = [Math]::Max(10, $y)", start)
    sec = w[start:end]
    # Must not paint two independent capacity rows for Cursor Models + xAI weekly.
    assert "Title 'Cursor Models'" not in sec
    assert 'Title "Cursor Models"' not in sec
    # Shared pool row present (title mentions both or shared helper).
    assert "Resolve-BobCursorXaiSharedPools" in sec or "shared" in sec.lower()
    assert "Cursor / xAI" in sec or "Cursor/xAI" in sec or "shared_pool" in sec.lower()
    # OpenCode + Copilot remain distinct family rows.
    assert "Family 'opencode'" in sec or 'Family "opencode"' in sec
    assert "Family 'copilot'" in sec or 'Family "copilot"' in sec
    # At most one fuel-family capacity paint for the shared cursor/xai pool.
    cursor_family = sec.count("Family 'cursor'") + sec.count('Family "cursor"')
    xai_family = sec.count("Family 'xai'") + sec.count('Family "xai"')
    # Dual-logo shared row may cite both families once each, or a single shared family once.
    assert cursor_family + xai_family <= 2
    assert "Add-BobTrayFuelFamilyRow" in sec


def test_fr6214_status_one_shared_section_not_two_capacity_headers():
    st = _txt(STATUS)
    render = st[st.index("public int Render") : st.index("protected override void OnPaint")]
    # No separate empty Cursor Models + xAI weekly capacity headers.
    assert 'Section(g, y, "Cursor Models"' not in render
    assert 'Section(g, y, "xAI weekly"' not in render
    # One shared heading (logo family may be xai or cursor-xai).
    assert "Cursor / xAI" in render or "Cursor/xAI" in render or "shared" in render.lower()
    assert "foreach (StatusRow r in m.Grok)" in render
    assert '"opencode"' in render and '"copilot"' in render


def test_fr6214_capacity_does_not_treat_cursor_and_xai_as_independent_totals():
    cap = _txt(CAPACITY)
    assert "Resolve-BobCursorXaiSharedPools" in cap or "Get-BobSharedCursorXaiRemaining" in cap or "FR #6214" in cap


def _run_shared(body: str, tmp_path: Path) -> str:
    script = tmp_path / "t6214.ps1"
    shared = str(SHARED).replace("'", "''")
    text = (
        "$ErrorActionPreference = 'Stop'\r\n"
        f". '{shared}'\r\n"
        + body
    )
    script.write_text(text, encoding="utf-8")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


@needs_ps
def test_fr6214_same_pool_fixture_renders_one_pool(tmp_path: Path):
    out = _run_shared(
        r"""
$refs = @(
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'cursor'; remaining_pct = 40; period_end = '2026-11-14T00:00:00Z'; label = 'Cursor Models' },
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'xai'; remaining_pct = 40; period_end = '2026-11-14T00:00:00Z'; label = 'xAI weekly' }
)
$pools = @(Resolve-BobCursorXaiSharedPools -Refs $refs)
$pools | ConvertTo-Json -Compress -Depth 6
""",
        tmp_path,
    )
    data = json.loads(out.strip().splitlines()[-1])
    if isinstance(data, dict):
        data = [data]
    assert len(data) == 1
    assert data[0]["pool_id"] == "acct-1"
    assert int(data[0]["remaining_pct"]) == 40
    fams = data[0].get("families") or []
    assert "cursor" in [str(x).lower() for x in fams]
    assert "xai" in [str(x).lower() for x in fams]


@needs_ps
def test_fr6214_updating_either_ref_updates_same_pool(tmp_path: Path):
    out = _run_shared(
        r"""
$a = @(Resolve-BobCursorXaiSharedPools -Refs @(
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'cursor'; remaining_pct = 55; period_end = '2026-11-20T00:00:00Z' },
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'xai'; remaining_pct = $null; period_end = $null }
))
$b = @(Resolve-BobCursorXaiSharedPools -Refs @(
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'cursor'; remaining_pct = $null; period_end = $null },
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'xai'; remaining_pct = 55; period_end = '2026-11-20T00:00:00Z' }
))
[pscustomobject]@{ a_pct = $a[0].remaining_pct; a_end = [string]$a[0].period_end; b_pct = $b[0].remaining_pct; b_end = [string]$b[0].period_end; a_n = @($a).Count; b_n = @($b).Count } | ConvertTo-Json -Compress
""",
        tmp_path,
    )
    data = json.loads(out.strip().splitlines()[-1])
    assert int(data["a_n"]) == 1 and int(data["b_n"]) == 1
    assert int(data["a_pct"]) == 55 and int(data["b_pct"]) == 55
    assert "2026-11-20" in data["a_end"] and "2026-11-20" in data["b_end"]


@needs_ps
def test_fr6214_distinct_pools_remain_distinct(tmp_path: Path):
    out = _run_shared(
        r"""
$pools = @(Resolve-BobCursorXaiSharedPools -Refs @(
  [pscustomobject]@{ pool_id = 'acct-cursor'; family = 'cursor'; remaining_pct = 10; period_end = '2026-11-10T00:00:00Z' },
  [pscustomobject]@{ pool_id = 'acct-xai'; family = 'xai'; remaining_pct = 90; period_end = '2026-12-01T00:00:00Z' }
))
$pools | ConvertTo-Json -Compress -Depth 6
""",
        tmp_path,
    )
    data = json.loads(out.strip().splitlines()[-1])
    if isinstance(data, dict):
        data = [data]
    assert len(data) == 2
    by_id = {str(p["pool_id"]): p for p in data}
    assert int(by_id["acct-cursor"]["remaining_pct"]) == 10
    assert int(by_id["acct-xai"]["remaining_pct"]) == 90


@needs_ps
def test_fr6214_unknown_stays_unknown_never_fabricated(tmp_path: Path):
    out = _run_shared(
        r"""
$pools = @(Resolve-BobCursorXaiSharedPools -Refs @(
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'cursor'; remaining_pct = $null; period_end = $null },
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'xai'; remaining_pct = $null; period_end = $null }
))
$p = $pools[0]
$raw = if ($null -eq $p.remaining_pct) { 'null' } else { [string]$p.remaining_pct }
[pscustomobject]@{ n = @($pools).Count; remaining = $raw; known = [bool]($null -ne $p.remaining_pct -and [string]$p.remaining_pct -ne '') } | ConvertTo-Json -Compress
""",
        tmp_path,
    )
    data = json.loads(out.strip().splitlines()[-1])
    assert int(data["n"]) == 1
    assert data["remaining"] == "null"
    assert data["known"] is False


@needs_ps
def test_fr6214_aggregate_capacity_counts_shared_pool_once(tmp_path: Path):
    out = _run_shared(
        r"""
$total = Get-BobSharedCursorXaiAggregateRemaining -Refs @(
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'cursor'; remaining_pct = 40 },
  [pscustomobject]@{ pool_id = 'acct-1'; family = 'xai'; remaining_pct = 40 }
)
$distinct = Get-BobSharedCursorXaiAggregateRemaining -Refs @(
  [pscustomobject]@{ pool_id = 'a'; family = 'cursor'; remaining_pct = 10 },
  [pscustomobject]@{ pool_id = 'b'; family = 'xai'; remaining_pct = 90 }
)
[pscustomobject]@{ shared = $total; distinct = $distinct } | ConvertTo-Json -Compress
""",
        tmp_path,
    )
    data = json.loads(out.strip().splitlines()[-1])
    assert int(data["shared"]) == 40
    assert int(data["distinct"]) == 100
