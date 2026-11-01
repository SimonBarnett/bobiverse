"""FR #5688: only fleet-backed Grok activity belongs in the public digest."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TRAY = Path(__file__).resolve().parents[1] / "tray" / "src"
PS = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(not PS, reason="needs PowerShell")
@pytest.mark.parametrize(
    "parent,lane,expected_running,expected_queued",
    [
        ("user", "", 0, 0),
        ("missing", "", 0, 0),
        ("cycle", "", 0, 0),
        ("reused", "", 0, 0),
        ("bob", "", 1, 0),
        ("hashed", "", 1, 0),
        ("impostor", "", 0, 0),
        ("indirect", "", 1, 0),
        ("user", "running", 1, 0),
        ("bob", "running", 1, 0),
        ("bob", "inbox", 0, 1),
        ("bob", "other", 2, 0),
    ],
)
def test_digest_counts_only_owned_unrepresented_sessions(
    tmp_path: Path, parent: str, lane: str, expected_running: int, expected_queued: int
):
    profile = tmp_path / "profile"
    (profile / ".grok").mkdir(parents=True)
    (profile / ".grok" / "active_sessions.json").write_text(
        json.dumps(
            [{"pid": 300, "session_id": "session-300", "cwd": "user-cwd",
              "opened_at": "2026-10-29T20:06:01Z"}]
        ),
        encoding="utf-8",
    )
    script = tmp_path / "test.ps1"
    script.write_text(
        f"""
New-Module -ReturnResult -ScriptBlock {{
$ErrorActionPreference = 'Stop'
. '{TRAY / "Public" / "Get-BobTrayHover.ps1"}'
. '{TRAY / "Private" / "Get-BobIrc.ps1"}'
. '{TRAY / "Private" / "Get-BobFleetPeek.ps1"}'
function Get-CimInstance {{
    $child = [pscustomobject]@{{ Name='grok.exe'; ProcessId=300; ParentProcessId=200;
        ExecutablePath='grok.exe'; CommandLine='grok.exe --cwd user-cwd';
        CreationDate=[datetime]'2026-10-29T20:06:00Z' }}
    $parent = [pscustomobject]@{{ Name='PriorityAgent.exe'; ProcessId=200; ParentProcessId=0;
        CreationDate=[datetime]'2026-10-29T20:00:00Z' }}
    switch ('{parent}') {{
        'bob' {{ $parent.Name = 'bob-worker.exe' }}
        'hashed' {{ $parent.Name = 'bob-worker-a1b2c3d4e5f6.exe' }}
        'impostor' {{ $parent.Name = 'bob-worker-unrelated.exe' }}
        'indirect' {{
            $parent.Name = 'cmd.exe'; $parent.ParentProcessId = 100
            [pscustomobject]@{{ Name='bob-worker.exe'; ProcessId=100; ParentProcessId=0;
                CreationDate=[datetime]'2026-10-29T19:00:00Z' }}
        }}
        'cycle' {{ $parent.ParentProcessId = 300 }}
        'reused' {{ $parent.Name = 'bob-worker.exe'; $parent.CreationDate = [datetime]'2026-10-30' }}
    }}
    $child
    if ('{parent}' -ne 'missing') {{ $parent }}
}}
function Get-ThisMachineId {{ 'test-box' }}
function Get-BobiverseConfig {{ [pscustomobject]@{{}} }}
function Get-BobIrcHome {{ '{tmp_path}' }}
function Get-BridgeRoot {{ '{tmp_path}' }}
function Get-BobPeerLaneJobs {{
    param($BridgeRoot, $MachineId, $Lane, [switch]$StampRepo)
    if ($Lane -eq '{lane}' -or ($Lane -eq 'running' -and '{lane}' -eq 'other')) {{
        [pscustomobject]@{{ id='lane-job'; sessionId=$(if ('{lane}' -eq 'other') {{ 'other-session' }} else {{ 'session-300' }});
            repo='SimonBarnett/fleet-repo'; claimedAt='2026-10-31T10:00:00Z' }}
    }}
}}
function Test-BobFleetJobProcessLive {{ param($Job, $OrphanSec) $true }}
function Get-BobWeeklyRemaining {{ $null }}
function Save-BobSeatPeriodEnd {{ param($MachineId, $PeriodEnd, $Weekly, [switch]$ClearWeekly) }}
function Get-BobCursorAgentWeeklyRemaining {{ $null }}
function Get-BobCursorPoolsForTray {{ param($MachineId, $LocalCursorDoc, $PcentRows, [switch]$LocalOnly) @() }}
function Get-BobGitShortSha {{ param($Cwd) 'abcdef0' }}
function Get-GitHubSlugFromCwd {{ param($Cwd) 'SimonBarnett/user-repo' }}
function Test-BobJobProcess {{ param($SessionId) $true }}
function Write-JsonFile {{ param($Path, $Doc) $Doc | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path }}
function Read-JsonFile {{ param($Path) Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }}
$all = @(Get-BobLiveGrokAgents)
if ($all.Count -ne 1 -or $all[0].pid -ne 300) {{ throw 'Unfiltered tray discovery changed' }}
$doc = Write-BobIrcStatus -PassThru -SkipDigestWebhook
$peer = Get-Content -LiteralPath (Join-Path '{tmp_path}' 'bob-peers/test-box.json') -Raw
@{{ doc=$doc; peer=$peer }} | ConvertTo-Json -Depth 10 -Compress
}}
""",
        encoding="utf-8-sig",
    )
    env = os.environ.copy()
    env["USERPROFILE"] = str(profile)
    env.pop("BOB_SKIP_LIVE_GROK", None)
    result = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert not result.stderr, result.stderr
    output = json.loads(result.stdout)
    doc = output["doc"]
    assert json.loads(output["peer"]) == doc
    assert doc["running"] == expected_running
    assert doc["queued"] == expected_queued
    assert len(doc["jobs"]) == expected_running + expected_queued
    if expected_running == 0:
        for field in ("repo", "sha", "started_at", "responding", "kind", "model"):
            assert doc[field] is None
    elif lane in ("running", "other"):
        assert doc["repo"] == "SimonBarnett/fleet-repo"
        assert doc["started_at"] == "2026-10-31T10:00:00Z"
    else:
        assert doc["repo"] == "SimonBarnett/user-repo"
        assert doc["started_at"]
        assert doc["responding"] is True
