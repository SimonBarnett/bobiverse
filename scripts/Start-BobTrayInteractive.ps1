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
    [string]$InstallRoot = 'C:\ai\bob',
    [string]$MachineId = '',
    [string]$TaskName = 'BobiverseTray',
    [string]$RunAsUser = '',
    [switch]$RunNow,
    [switch]$RegisterOnly
)

$ErrorActionPreference = 'Stop'
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
$tr = ('"{0}" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" -InstallRoot "{2}" -MachineId {3} -ForceNew' -f $ps, $tray, $InstallRoot, $MachineId)

# Prefer explicit user; else Administrator when present; else current user.
if (-not $RunAsUser) {
    if (Test-Path 'C:\Users\Administrator') { $RunAsUser = 'Administrator' }
    else { $RunAsUser = $env:USERNAME }
}

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
# /IT = only when user is logged on interactively; /RL LIMITED = no elevation needed for UI
$create = schtasks /Create /TN $TaskName /SC ONLOGON /RU $RunAsUser /RL LIMITED /IT /F /TR $tr 2>&1
Write-Host ("INFO schtasks create {0}: {1}" -f $TaskName, (($create | Out-String).Trim()))

if ($RunNow -and -not $RegisterOnly) {
    $run = schtasks /Run /TN $TaskName 2>&1
    Write-Host ("INFO schtasks run {0}: {1}" -f $TaskName, (($run | Out-String).Trim()))
}

Write-Host "INFO Start-BobTrayInteractive done user=$RunAsUser machine=$MachineId"
