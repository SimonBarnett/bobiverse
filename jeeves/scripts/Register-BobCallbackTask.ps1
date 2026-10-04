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
# FR #1316 / MRB #1353: never re-register as LocalSystem / SYSTEM (S-1-5-18) against a user profile home.
$ruNorm = ($RunAsUser -replace '^.*\\', '').Trim()
if (
    $ruNorm -match '^(SYSTEM|LOCALSYSTEM|LOCAL SERVICE|NETWORK SERVICE)$' -or
    $RunAsUser -match 'S-1-5-18' -or
    $RunAsUser -match '(?i)NT AUTHORITY\\SYSTEM'
) {
    throw ("Refuse RunAsUser={0}: BobCallback must not run as LocalSystem/SYSTEM (FR #1316). Pass the digest-home owner (e.g. Administrator)." -f $RunAsUser)
}

# FR #1455: supervise bobcallback in a restart loop. A bare python action exits to
# Ready after any kill/wedge; Start-ScheduledTask then often fails to bind under
# Interactive logon from a non-interactive seat. The wrapper keeps :7700 alive.
$supervise = Join-Path $here 'Start-BobCallbackSupervised.ps1'
if (-not (Test-Path -LiteralPath $supervise)) {
    $supervise = Join-Path (Split-Path -Parent $ScriptPath) 'Start-BobCallbackSupervised.ps1'
}
if (Test-Path -LiteralPath $supervise) {
    $psArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Python "{1}" -ScriptPath "{2}" -DigestHome "{3}" -Port {4}' -f `
        $supervise, $Python, $ScriptPath, $DigestHome, $Port
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
    Write-Host ("INFO BobCallback action=supervised wrapper={0}" -f $supervise)
} else {
    $arg = '-u "{0}" --home "{1}" --bind 127.0.0.1 --port {2}' -f $ScriptPath, $DigestHome, $Port
    $action = New-ScheduledTaskAction -Execute $Python -Argument $arg
    Write-Host 'WARN Start-BobCallbackSupervised.ps1 missing; registering bare python action'
}
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

function Test-BobCallbackPortListen {
    param([int]$Port = 7700)
    try {
        $c = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return [bool]$c
    } catch { return $false }
}

if ($Start) {
    try {
        Start-ScheduledTask -TaskName 'BobCallback'
        Write-Host 'INFO Start-ScheduledTask BobCallback'
    } catch {
        Write-Host ("WARN Start-ScheduledTask: {0}" -f $_.Exception.Message)
    }
    $deadline = (Get-Date).AddSeconds(12)
    while ((Get-Date) -lt $deadline -and -not (Test-BobCallbackPortListen -Port $Port)) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-BobCallbackPortListen -Port $Port)) {
        # Interactive tasks often do not bind when started from a non-interactive seat;
        # fall back to same-user Start-Process (FR #1316 / Start-Jeeves wedge path).
        # FR #1455: prefer supervised wrapper so a later kill still auto-restarts.
        Write-Host 'WARN BobCallback not listening after task start; heal carefully (FR #1767/#1831)'
        # Count supervised parents before any Start-Process (monitor heal races).
        $supParents = 0
        try {
            foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" -ErrorAction SilentlyContinue)) {
                if ([string]$p.CommandLine -match 'Start-BobCallbackSupervised\.ps1') { $supParents++ }
            }
        } catch { }
        if ($supParents -ge 1) {
            Write-Host ("WARN skip Start-Process fallback; already {0} supervised parent(s) (FR #1767)" -f $supParents)
            try { schtasks /Run /TN BobCallback 2>&1 | Out-Null } catch { }
        } elseif (Test-Path -LiteralPath $supervise) {
            try { Stop-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue } catch { }
            Start-Sleep -Seconds 1
            $fbArgs = @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $supervise,
                '-Python', $Python, '-ScriptPath', $ScriptPath, '-DigestHome', $DigestHome, '-Port', "$Port"
            )
            Start-Process -FilePath 'powershell.exe' -ArgumentList $fbArgs -WindowStyle Hidden | Out-Null
            Write-Host 'INFO fallback launched Start-BobCallbackSupervised.ps1'
        } else {
            try { Stop-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue } catch { }
            Start-Sleep -Seconds 1
            $argList = @('-u', $ScriptPath, '--home', $DigestHome, '--bind', '127.0.0.1', '--port', "$Port")
            Start-Process -FilePath $Python -ArgumentList $argList -WindowStyle Hidden | Out-Null
        }
        $deadline2 = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline2 -and -not (Test-BobCallbackPortListen -Port $Port)) {
            Start-Sleep -Milliseconds 500
        }
        if (Test-BobCallbackPortListen -Port $Port) {
            Write-Host ("INFO bobcallback listening via user-context fallback port={0}" -f $Port)
        } else {
            Write-Host ("WARN bobcallback still not listening on 127.0.0.1:{0}" -f $Port)
        }
    } else {
        Write-Host ("INFO bobcallback listening on 127.0.0.1:{0}" -f $Port)
    }
}
