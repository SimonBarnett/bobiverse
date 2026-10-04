#Requires -Version 5.1
<#
.SYNOPSIS
  Start TipForm in an interactive logon session (never session 0).
.DESCRIPTION
  Quiet MSI / airc install often runs in session 0. TipForm must appear on the
  console/RDP desktop. This registers (or runs) a logon task with /IT so
  Start-BobTray.ps1 lands in the interactive session.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',   # '' = installed root / discovered <ai root>\bob (t780u)
    [string]$MachineId = '',
    [string]$TaskName = 'BobiverseTray',
    # FR #1642: minute probe that relaunches Start-BobTray -ForceNew -SkipTidy when the tray dies unexpectedly.
    [string]$WatchdogTaskName = 'BobiverseTrayWatchdog',
    [int]$WatchdogMinutes = 1,
    [string]$RunAsUser = '',
    [switch]$RunNow,
    [switch]$RegisterOnly,
    # #32 / FR #1636: SkipTidy is the default for ONLOGON + Startup shortcuts so logon/autostart
    # does not kill seats / Grok Bot. TipForm menu Restart remains the explicit "tidy everything" path.
    [switch]$SkipTidy
)

$ErrorActionPreference = 'Stop'
# t780u: no hard-coded C:\ai. Installed: this script lives in <install>\scripts, so the install root is its parent. Otherwise the
# <drive>:\ai root is discovered on the fixed disks (Bobiverse-Common.ps1; BOB_AI_ROOT overrides).
if (-not $InstallRoot) {
    $selfRoot = Split-Path -Parent $PSScriptRoot
    $cm = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath (Join-Path $selfRoot 'tools\Watch-BobTray.ps1')) { $InstallRoot = $selfRoot }
    elseif (Test-Path -LiteralPath $cm) { . $cm; $InstallRoot = Get-BobiverseProductRoot -Product bob }
    else { $InstallRoot = $selfRoot }
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$tray = Join-Path $InstallRoot 'scripts\Start-BobTray.ps1'
if (-not (Test-Path -LiteralPath $tray)) { throw "missing $tray" }

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}

$ps = (Get-Command powershell.exe).Source
# FR #1636: persistent ONLOGON / Startup always -ForceNew -SkipTidy (replace prior tray only; keep seats).
$trayArgsPersistent = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId {0} -ForceNew -SkipTidy" -f $MachineId
$tr = ('"{0}" {1}' -f $ps, $trayArgsPersistent)

# Prefer explicit user; else Administrator when present; else current user.
if (-not $RunAsUser) {
    if (Test-Path 'C:\Users\Administrator') { $RunAsUser = 'Administrator' }
    else { $RunAsUser = $env:USERNAME }
}

$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
# Missing task -> Delete errors; ignore so Create still runs.
cmd /c "schtasks /Delete /TN `"$TaskName`" /F >nul 2>&1" | Out-Null
# /IT = interactive session only; /RL LIMITED = TipForm UI (no elevation).
# Workgroup Admin ONLOGON may need a password; prefer Register-ScheduledTask when available.
$created = $false
try {
    $action = New-ScheduledTaskAction -Execute $ps -Argument $trayArgsPersistent
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
    $principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force -ErrorAction Stop | Out-Null
    $created = $true
    Write-Host ("INFO Register-ScheduledTask {0} user={1} (ForceNew+SkipTidy FR #1636)" -f $TaskName, $RunAsUser)
} catch {
    Write-Host ("WARN Register-ScheduledTask: {0}" -f $_.Exception.Message)
    $create = cmd /c "schtasks /Create /TN `"$TaskName`" /SC ONLOGON /RU `"$RunAsUser`" /RL LIMITED /IT /F /TR $tr"
    Write-Host ("INFO schtasks create {0}: {1}" -f $TaskName, (($create | Out-String).Trim()))
    if ($LASTEXITCODE -eq 0) { $created = $true }
}
if ($RunNow -and -not $RegisterOnly) {
    if ($created) {
        # Persistent task already has SkipTidy; RunNow just starts it (seats/Grok Bot kept).
        $run = cmd /c "schtasks /Run /TN `"$TaskName`""
        Write-Host ("INFO schtasks run {0}: {1}" -f $TaskName, (($run | Out-String).Trim()))
    }
    # Also drop Startup shortcut for Administrator so next logon is covered.
    $adminStartup = 'C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
    if (Test-Path -LiteralPath $adminStartup) {
        $lnk = Join-Path $adminStartup 'Bobiverse Tray.lnk'
        $ws = New-Object -ComObject WScript.Shell
        $s = $ws.CreateShortcut($lnk)
        $s.TargetPath = $ps
        $s.Arguments = $trayArgsPersistent
        $s.WorkingDirectory = $InstallRoot
        $s.Description = 'bob TipForm (interactive; SkipTidy FR #1636)'
        $s.Save()
        Write-Host "INFO Startup shortcut $lnk (SkipTidy)"
    }
}
# FR #1642: register unexpected-exit watchdog (SkipTidy only; never tidies seats).
$ensure = Join-Path $InstallRoot 'scripts\Ensure-BobTrayRunning.ps1'
if (Test-Path -LiteralPath $ensure) {
    cmd /c "schtasks /Delete /TN `"$WatchdogTaskName`" /F >nul 2>&1" | Out-Null
    $wdArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ensure`" -InstallRoot `"$InstallRoot`" -MachineId {0}" -f $MachineId
    try {
        $wdAction = New-ScheduledTaskAction -Execute $ps -Argument $wdArgs
        $wdLogon = New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
        $wdWatch = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes ([Math]::Max(1, $WatchdogMinutes))) `
            -RepetitionDuration (New-TimeSpan -Days 9999)
        $wdSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $wdPrincipal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $WatchdogTaskName -Action $wdAction -Trigger @($wdLogon, $wdWatch) `
            -Settings $wdSettings -Principal $wdPrincipal -Force -ErrorAction Stop | Out-Null
        Write-Host ("INFO Register-ScheduledTask {0} every {1}m (ForceNew+SkipTidy relaunch FR #1642)" -f $WatchdogTaskName, $WatchdogMinutes)
    } catch {
        Write-Host ("WARN Register-ScheduledTask {0}: {1}" -f $WatchdogTaskName, $_.Exception.Message)
        $wdTr = ('"{0}" {1}' -f $ps, $wdArgs)
        $createWd = cmd /c "schtasks /Create /TN `"$WatchdogTaskName`" /SC MINUTE /MO $WatchdogMinutes /RU `"$RunAsUser`" /RL LIMITED /IT /F /TR $wdTr"
        Write-Host ("INFO schtasks create {0}: {1}" -f $WatchdogTaskName, (($createWd | Out-String).Trim()))
    }
} else {
    Write-Host ("WARN missing {0}; BobiverseTrayWatchdog not registered" -f $ensure)
}

$ErrorActionPreference = $prevEap

Write-Host "INFO Start-BobTrayInteractive done user=$RunAsUser machine=$MachineId"
