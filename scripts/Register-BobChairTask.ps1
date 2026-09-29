# Keep Jeeves (digest chair) alive as the interactive user, not LocalSystem.
# Why not the NSSM service as LocalSystem: irc_agent loads a DPAPI user-scope
# identity (seal identity.json, AIRC1) and runs icacls for USERDOMAIN\USERNAME;
# as SYSTEM both fail (icacls 1332) and the chair crash-loops. Worse, each
# Install-BobChair start first stops the live chair, so a crash-looping service
# keeps killing Jeeves. Run this once as the chair user (elevated).
#
# One task instance == one Jeeves lifetime (Install-BobChair blocks on python).
# MultipleInstances IgnoreNew + a repetition trigger = watchdog: a new instance
# only starts when the previous chair has exited (<= WatchMinutes gap after a
# crash). Task Scheduler RestartOnFailure only covers LAUNCH failures, not a
# non-zero exit, so the repetition trigger is the real watchdog.
# Own log file: a shared log held open by another launcher makes *>> fail silently.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$TaskName = 'BobJeeves-chair',
    [int]$WatchMinutes = 1,
    [string]$IrcHost = 'irc.ntsa.uk',
    [int]$Port = 6697,
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$chair = Join-Path $here 'Install-BobChair.ps1'
if (-not (Test-Path -LiteralPath $chair)) { throw "missing $chair" }
$user = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
if ($env:USERNAME -like '*$') { throw 'run as the chair user, not a machine/service account' }
$logDir = Join-Path $env:USERPROFILE '.grok\long-running-background-tasks'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'bobjeeves-chair-task.log'

$cmd = "& '$chair' --host $IrcHost --port $Port *>> '$log'; exit `$LASTEXITCODE"
$arg = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "' + $cmd + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg -WorkingDirectory $here
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$watch = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $WatchMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 9999)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($atLogon, $watch) `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "registered $TaskName as $user (watch every ${WatchMinutes}m, IgnoreNew)"
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "started $TaskName"
}
