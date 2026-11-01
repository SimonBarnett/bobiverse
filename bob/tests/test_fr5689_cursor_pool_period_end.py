"""Cursor billing periods must not be pinned by heartbeat cache writeback."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
PS = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not PS, reason="needs PowerShell")
PAST = "2026-10-16T17:23:01Z"
FRESH = "2099-11-07T12:58:59Z"
SAND = "2099-11-03T12:00:00Z"


@pytest.fixture
def run_ps(tmp_path):
    cache = tmp_path / "cursor-pools.json"
    prelude = """
$ErrorActionPreference = 'Stop'
. (Join-Path $env:TEST_REPO 'bob/tray/src/Private/Get-BobIrc.ps1')
. (Join-Path $env:TEST_REPO 'bob/tray/src/Public/Get-BobTrayHover.ps1')
function Get-BobCursorPoolsCachePath { return $env:TEST_CACHE }
function Read-JsonFile($Path) {
    $options = @{}
    if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) { $options.DateKind = 'String' }
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json @options
}
function Write-JsonFile($Path, $Doc) { $Doc | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path }
function Get-BobSeatForMachine { [pscustomobject]@{ id = 'test-seat'; label = 'Test' } }
function Format-BobResetLabel { param($PeriodEnd, $FetchedAt); return $PeriodEnd }
"""

    def run(body, entry=None):
        cache.write_text(json.dumps({"by_seat": {"test-seat": entry or {}}}), encoding="utf-8")
        script = tmp_path / "run.ps1"
        script.write_text(prelude + body, encoding="utf-8")
        result = subprocess.run(
            [PS, "-NoProfile", "-File", str(script)],
            env=dict(os.environ, TEST_REPO=str(ROOT), TEST_CACHE=str(cache)),
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout), json.loads(cache.read_text(encoding="utf-8-sig"))

    return run


@pytest.mark.parametrize("local_only", [True, False])
@pytest.mark.parametrize("auto_id", ["auto", "low-cost-models"])
@pytest.mark.parametrize("cached_end", [PAST, "2099-11-01T00:00:00Z", "2099-12-01T00:00:00Z"])
def test_published_rows_prefer_fresh_billing_end(run_ps, local_only, auto_id, cached_end):
    rows, saved = run_ps(
        f"""
$local = [pscustomobject]@{{
    period_end = '{FRESH}'; sand_period_end = '{SAND}'
    cursor_spending_groups = @(
        [pscustomobject]@{{ id = 'high-cost-models'; remaining_pct = 100 }}
        [pscustomobject]@{{ id = 'auto'; remaining_pct = 57 }}
        [pscustomobject]@{{ id = 'grok-chat'; remaining_pct = 0 }}
    )
}}
$pools = @(Get-BobCursorPoolsForTray -MachineId test -LocalCursorDoc $local -LocalOnly:${str(local_only).lower()})
foreach ($pool in $pools) {{
    Save-BobCursorPoolGroupForSeat -SeatId test-seat -GroupId $pool.group_id -RemainingPct $pool.remaining_pct -PeriodEnd $pool.period_end
}}
@(ConvertTo-BobDigestCursorPoolRows -Pools $pools) | ConvertTo-Json -Depth 10
""",
        {"groups": {
            auto_id: {"remaining_pct": 1, "period_end": cached_end},
            "high-cost-models": {"remaining_pct": 2, "period_end": cached_end},
            "grok-chat": {"remaining_pct": 3, "period_end": cached_end},
        }},
    )
    by = {row["group_id"]: row for row in rows}
    for gid, remaining in [("auto", 57), ("high-cost-models", 100), ("grok-chat", 0)]:
        expected_end = SAND if gid == "grok-chat" else FRESH
        assert by[gid]["remaining_pct"] == remaining
        assert by[gid]["period_end"] == expected_end
        assert saved["by_seat"]["test-seat"]["groups"][gid]["period_end"] == expected_end


def test_read_drops_expired_dates_and_their_stale_remaining(run_ps):
    read, _ = run_ps(
        "Read-BobCursorPoolsCache | ConvertTo-Json -Depth 10",
        {"period_end": PAST, "groups": {
            "auto": {"period_end": PAST, "remaining_pct": 57},
            "grok-chat": {"period_end": PAST, "remaining_pct": 0},
            "high-cost-models": {"period_end": FRESH, "remaining_pct": 100},
        }},
    )
    seat = read["by_seat"]["test-seat"]
    assert not seat.get("period_end")
    for gid, remaining in [("auto", 57), ("grok-chat", 0)]:
        assert not seat["groups"][gid].get("period_end")
        assert seat["groups"][gid].get("remaining_pct") is None
    assert seat["groups"]["high-cost-models"]["period_end"] == FRESH
    assert seat["groups"]["high-cost-models"]["remaining_pct"] == 100


@pytest.mark.parametrize("group_id", ["auto", "grok-chat"])
@pytest.mark.parametrize("existing_end", [PAST, FRESH])
def test_save_rejects_expired_dates_and_preserves_current_dates(run_ps, group_id, existing_end):
    _, saved = run_ps(
        f"""
Save-BobCursorPoolGroupForSeat -SeatId test-seat -GroupId '{group_id}' -RemainingPct 0 -PeriodEnd '{PAST}'
Read-BobCursorPoolsCache | ConvertTo-Json -Depth 10
""",
        {"groups": {group_id: {"period_end": existing_end, "remaining_pct": 57}}},
    )
    group = saved["by_seat"]["test-seat"]["groups"][group_id]
    assert group.get("remaining_pct") == (57 if existing_end == FRESH else None)
    assert group.get("period_end") == (FRESH if existing_end == FRESH else None)


@pytest.mark.parametrize("local_only", [True, False])
def test_valid_cached_end_fills_missing_billing_end_without_becoming_sand(run_ps, local_only):
    rows, _ = run_ps(
        f"""
$local = [pscustomobject]@{{ cursor_spending_groups = @(
    [pscustomobject]@{{ id = 'auto'; remaining_pct = 0 }}
) }}
@(Get-BobCursorPoolsForTray -MachineId test -LocalCursorDoc $local -LocalOnly:${str(local_only).lower()}) | ConvertTo-Json -Depth 10
""",
        {"groups": {"low-cost-models": {"period_end": FRESH, "remaining_pct": 57}}},
    )
    by = {row["group_id"]: row for row in rows}
    assert by["auto"]["period_end"] == FRESH
    assert by["auto"]["remaining_pct"] == 0
    assert not by["grok-chat"]["period_end"]


def test_expired_sand_is_not_republished_without_fresh_sand_usage(run_ps):
    rows, _ = run_ps(
        f"""
$local = [pscustomobject]@{{ period_end = '{FRESH}' }}
@(Get-BobCursorPoolsForTray -MachineId test -LocalCursorDoc $local -LocalOnly) | ConvertTo-Json -Depth 10
""",
        {"groups": {"grok-chat": {"period_end": PAST, "remaining_pct": 0}}},
    )
    sand = next(row for row in rows if row["group_id"] == "grok-chat")
    assert sand["remaining_pct"] is None
    assert not sand["period_end"]


def test_legacy_seat_save_also_rejects_expired_billing_end(run_ps):
    _, saved = run_ps(
        f"""
Save-BobCursorPoolForSeat -SeatId test-seat -RemainingPct 0 -Label '0%' -PeriodEnd '{PAST}'
Read-BobCursorPoolsCache | ConvertTo-Json -Depth 10
""",
        {"period_end": PAST, "remaining_pct": 57},
    )
    seat = saved["by_seat"]["test-seat"]
    assert not seat.get("period_end")
    assert seat.get("remaining_pct") is None
