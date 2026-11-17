"""FR #7998: stall-alerts must not call Get-BobHealth (two 30s timeouts)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

SRC = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobStallAlerts.ps1"


def test_fr7998_stall_alerts_does_not_call_full_health():
    text = SRC.read_text(encoding="utf-8")
    assert "Get-BobHealth" not in text
    assert "Get-BobAgents" not in text
    # One snapshot inside Get-BobStallAlerts, plus the old per-session fallback.
    assert text.count("Get-CimInstance") == 2
    assert "TimeoutSec 5" in text
    assert "FR #7998" in text


def test_fr7998_stall_alerts_uses_one_snapshot_and_finishes(tmp_path: Path):
    claimed = "2020-01-01T00:00:00Z"
    script = tmp_path / "run.ps1"
    script.write_text(
        r"""
$ErrorActionPreference = 'Stop'
. '%s'
function Get-BobMachineRecord { return @{ lastSeen = '2020-01-01T00:00:00Z' } }
function Get-BobLastSeenAgeSec { param($Record) 1000 }
function Test-BobWatcherInstalled { return $true }
function Get-BobBuilds {
    param([string]$Lane)
    if ($Lane -eq 'running') {
        return @([pscustomobject]@{ id = 'job-1'; sessionId = 'sess-missing'; claimedAt = '%s' })
    }
    return @()
}
function Test-GrokBotAvailable { return $false }
$seen = @{ inbox = @{}; running = @{}; stall = @{} }
$rows = @(
    [pscustomobject]@{ Name = 'notepad.exe'; CommandLine = 'notepad' }
)
$sw = [Diagnostics.Stopwatch]::StartNew()
$alerts = @(Get-BobStallAlerts -Seen $seen -StallSec 600 -HeartbeatStaleSec 90 -ProcessRows $rows)
$sw.Stop()
if ($sw.Elapsed.TotalSeconds -ge 5) { throw ('too slow ' + $sw.Elapsed.TotalSeconds) }
$joined = $alerts -join '|'
if ($joined -notmatch 'running_orphan') { throw ('missing orphan: ' + $joined) }
if ($joined -notmatch 'watcher_down') { throw ('missing watcher: ' + $joined) }
Write-Output 'ok'
"""
        % (str(SRC).replace("'", "''"), claimed),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout
