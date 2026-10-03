<#
.SYNOPSIS
  Register scheduled task BobCallback as the account that owns the digest home (FR #1316).

.DESCRIPTION
  Install-Jeeves historically registered BobCallback as LocalSystem while --home pointed at
  C:\Users\Administrator\.bobiverse. Cross-principal digest.lock / ACL fights wedge :7700.
  This registers BobCallback as the interactive Administrator (or -RunAsUser) that owns
  the home so lock + writes match the chair digest writers / user-context restores.

.PARAMETER DigestHome
  Path passed as --home (default: BOB_DIGEST_HOME or ~\.bobiverse).

.PARAMETER Python
  Python executable.

.PARAMETER ScriptPath
  bobcallback.py path (default: beside this script).

.PARAMETER RunAsUser
  Windows account for the task (default: current user / Administrator).

.PARAMETER Port
  Listen port (default 7700).
#>
[CmdletBinding()]
param(
    [string]$DigestHome = '',
    [string]$Python = '',
    [string]$ScriptPath = '',
    [string]$RunAsUser = '',
    [int]$Port = 7700,
    [switch]$Start
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptPath) {
    $ScriptPath = Join-Path $here 'bobcallback.py'
}
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "bobcallback.py not found: $ScriptPath"
}
if (-not $DigestHome) {
    $DigestHome = $env:BOB_DIGEST_HOME
}
if (-not $DigestHome) {
    $DigestHome = Join-Path $env:USERPROFILE '.bobiverse'
}
$DigestHome = [System.IO.Path]::GetFullPath($DigestHome)
if (-not $Python) {
    $common = Join-Path $here 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath $common) {
        . $common
        if (Get-Command Resolve-BobiversePython -ErrorAction SilentlyContinue) {
            $Python = Resolve-BobiversePython
        }
    }
}
if (-not $Python) { $Python = 'python' }
if (-not $RunAsUser) {
    $RunAsUser = if ($env:USERNAME) { $env:USERNAME } else { 'Administrator' }
}

$arg = '-u "{0}" --home "{1}" --bind 127.0.0.1 --port {2}' -f $ScriptPath, $DigestHome, $Port
$action = New-ScheduledTaskAction -Execute $Python -Argument $arg
# Interactive: same account as the profile that owns .bobiverse (no password stored).
$principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Unregister-ScheduledTask -TaskName 'BobCallback' -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName 'BobCallback' -Action $action -Principal $principal `
    -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host ("INFO registered BobCallback runAs={0} home={1} port={2} (FR #1316)" -f $RunAsUser, $DigestHome, $Port)

if ($Start) {
    try {
        Start-ScheduledTask -TaskName 'BobCallback'
        Write-Host 'INFO Start-ScheduledTask BobCallback'
    } catch {
        Write-Host ("WARN Start-ScheduledTask: {0}" -f $_.Exception.Message)
    }
}
