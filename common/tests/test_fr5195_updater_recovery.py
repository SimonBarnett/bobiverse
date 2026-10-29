"""FR #5195: execute updater functions with mocked Windows service/installer APIs."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "common/scripts/Update-BobiverseService.ps1"
PS = shutil.which("pwsh") or shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(not PS, reason="PowerShell required")


def run_ps(tmp_path, body):
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$tokens=$null; $errors=$null\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{UPDATER}',"
        "[ref]$tokens,[ref]$errors)\n"
        "if ($errors.Count) { throw $errors[0] }\n"
        "$ast.FindAll({param($n) $n -is "
        "[System.Management.Automation.Language.FunctionDefinitionAst]},$false) | "
        "ForEach-Object { . ([scriptblock]::Create($_.Extent.Text.Replace("
        f"'$PSScriptRoot', \"'{UPDATER.parent}'\"))) }}\n"
        + body,
        encoding="utf-8",
    )
    result = subprocess.run(
        [PS, "-NoProfile", "-File", str(harness)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize("outcome", [
    "launch-failed", "install-failed", "timeout", "fallback-timeout",
    "rollback-failed", "state-write-failed", "success",
])
def test_apply_always_restarts_after_stop(tmp_path, outcome):
    root = tmp_path / "install"
    root.mkdir()
    (root / "VERSION").write_text("1.0.3")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "tag": "v1.0.7", "version": "1.0.7", "msiName": "bob-1.0.7.msi",
        "msiUrl": "FAKE_MSI", "shaUrl": "FAKE_SHA",
    }))
    body = f"""
$Product='bob'; $ServiceName='ircBob'; $InstallRoot='{root}'; $StateDir='{tmp_path}'
$PlanFile='{plan}'; $DelaySeconds=0; $VerifyOnly=$false
$script:StateFile=Join-Path $StateDir 'state.json'; $script:LogFile=Join-Path $StateDir 'update.log'
$script:status='Running'; $script:starts=0; $script:stops=0
$script:events=[Collections.Generic.List[string]]::new()
function Get-Service {{ [pscustomobject]@{{Status=$script:status}} }}
function Stop-Service {{ $script:events.Add('stop'); $script:status='Stopped'; $script:stops++ }}
function Start-Service {{ $script:events.Add('start'); $script:status='Running'; $script:starts++ }}
function Wait-ServiceState {{ param($Name,$Status,$Seconds) return $script:status -eq $Status }}
function Start-Sleep {{ }}
function Get-Asset {{ param($Url,$Dest)
    if ($Url -eq 'FAKE_MSI') {{ Set-Content $Dest 'payload' }}
    else {{ Set-Content $Dest ('a'*64) }}
}}
function Get-FileHash {{ [pscustomobject]@{{Hash=('a'*64)}} }}
function Backup-Install {{ $script:events.Add('backup'); return 'FAKE_BACKUP' }}
function Register-ServiceWatchdog {{ $script:events.Add('watchdog') }}
function Get-ServiceAppParameters {{ return '' }}
function Get-BobiverseArpProduct {{ return $null }}
function Update-SkillsInProfiles {{ }}
function Remove-OldBackups {{ }}
function Invoke-Rollback {{
    $script:events.Add('rollback')
    if ('{outcome}' -eq 'rollback-failed') {{ throw 'rollback failed' }}
    Start-Service
}}
function Unregister-ScheduledTask {{ }}
function Invoke-BobiverseMsiexecSerialized {{
    $script:events.Add('install')
    if ('{outcome}' -eq 'launch-failed') {{ throw 'installer did not launch' }}
    if ('{outcome}' -eq 'timeout') {{ throw 'msiexec timed out' }}
    if ('{outcome}' -in @('rollback-failed','state-write-failed')) {{ throw 'install failed' }}
    if ('{outcome}' -eq 'install-failed') {{ return [pscustomobject]@{{ExitCode=1603}} }}
    Set-Content (Join-Path $InstallRoot 'VERSION') '1.0.7'
    return [pscustomobject]@{{ExitCode=0}}
}}
if ('{outcome}' -eq 'state-write-failed') {{ function Save-State {{ throw 'state disk unavailable' }} }}
if ('{outcome}' -eq 'fallback-timeout') {{
    Remove-Item Function:Invoke-BobiverseMsiexecSerialized
    $env:SystemRoot=$StateDir
    function Start-Process {{
        $p=[pscustomobject]@{{Handle=1; ExitCode=0}}
        $p | Add-Member ScriptMethod WaitForExit {{ param($ms) return $false }}
        return $p
    }}
}}
try {{ Invoke-Apply }} catch {{
    if ('{outcome}' -notin @('rollback-failed','state-write-failed')) {{ throw }}
}}
if ($script:status -ne 'Running' -or $script:starts -lt 1) {{ throw 'ear left stopped' }}
if ($script:stops -ne 1) {{ throw 'wrong stop count' }}
if ($script:events.IndexOf('backup') -gt $script:events.IndexOf('stop')) {{ throw 'backup consumed downtime' }}
if ($script:events.IndexOf('watchdog') -lt 0 -or
    $script:events.IndexOf('watchdog') -gt $script:events.IndexOf('stop')) {{ throw 'stop without watchdog' }}
if (Test-Path (Join-Path $StateDir 'downtime.json')) {{ throw 'downtime lease not cleared' }}
if ('{outcome}' -eq 'success') {{
    if ((Get-State).lastResult -ne 'updated') {{ throw 'update not recorded' }}
    if ((Get-Content (Join-Path $InstallRoot 'VERSION')).Trim() -ne '1.0.7') {{ throw 'wrong version' }}
}}
"""
    run_ps(tmp_path, body)


@pytest.mark.parametrize("timestamp", ["2000-01-01T00:00:00Z", "bad", "2999-01-01T00:00:00Z"])
@pytest.mark.parametrize("task_running", [True, False])
def test_pending_has_bounded_ttl_even_with_running_task(tmp_path, timestamp, task_running):
    (tmp_path / "VERSION").write_text("1.0.3")
    (tmp_path / "state.json").write_text(json.dumps({
        "pending": {"tag": "v1.0.7", "atUtc": timestamp},
    }))
    output = run_ps(tmp_path, f"""
$Product='bob'; $InstallRoot='{tmp_path}'; $StateDir='{tmp_path}'
$script:StateFile=Join-Path $StateDir 'state.json'; $script:LogFile=Join-Path $StateDir 'update.log'
$script:PendingMinutes=40; $ReleaseJson='FAKE'; $ForceCheck=$false
function Get-OptOutReason {{ return $null }}
function Get-ScheduledTask {{ [pscustomobject]@{{State='{"Running" if task_running else "Ready"}'}} }}
function Get-LatestRelease {{ return $null }}
Invoke-Check
if ((Get-State).pending) {{ throw 'stale pending retained' }}
""")
    assert "skipped-pending" not in output


def test_watchdog_is_registered_as_recurring_system_task(tmp_path):
    run_ps(tmp_path, f"""
$Product='bob'; $ServiceName='ircBob'; $InstallRoot='{tmp_path}'; $StateDir='{tmp_path}'
function New-ScheduledTaskAction {{ param($Execute,$Argument)
    if ($Argument -notlike '*Watch-BobiverseService.ps1*') {{ throw 'not watchdog' }}
    [pscustomobject]@{{Execute=$Execute;Argument=$Argument}}
}}
function New-ScheduledTaskPrincipal {{ param($UserId,$LogonType,$RunLevel)
    if ($UserId -ne 'SYSTEM' -or $RunLevel -ne 'Highest') {{ throw 'wrong principal' }}
    return 'principal'
}}
function New-ScheduledTaskTrigger {{ param([switch]$Once,$At,$RepetitionInterval)
    if ($RepetitionInterval.TotalSeconds -ne 60) {{ throw 'not once a minute' }}
    return 'trigger'
}}
function New-ScheduledTaskSettingsSet {{ param([switch]$AllowStartIfOnBatteries,
    [switch]$DontStopIfGoingOnBatteries,[switch]$StartWhenAvailable,$ExecutionTimeLimit,$MultipleInstances)
    if ($ExecutionTimeLimit.TotalSeconds -ne 120) {{ throw 'unbounded watchdog' }}
    if ($MultipleInstances -ne 'IgnoreNew') {{ throw 'overlapping watchdogs' }}
    return 'settings'
}}
function Register-ScheduledTask {{ param($TaskName,$Action,$Principal,$Trigger,$Settings,[switch]$Force,$ErrorAction)
    if ($TaskName -ne 'bobiverse-watchdog-bob' -or -not $Trigger) {{ throw 'not recurring watchdog' }}
    $script:registered=$true
}}
Register-ServiceWatchdog
if (-not $script:registered) {{ throw 'not registered' }}
if (-not (Test-Path (Join-Path $StateDir 'run/Watch-BobiverseService.ps1'))) {{ throw 'missing detached copy' }}
""")
