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
    [string]$RunAsUser = '',
    [switch]$RunNow,
    [switch]$RegisterOnly,
    # #32: RunNow must not kill seats / Grok Bot. The persistent logon task keeps the normal tidy.
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
$tr = ('"{0}" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "{1}" -InstallRoot "{2}" -MachineId {3} -ForceNew' -f $ps, $tray, $InstallRoot, $MachineId)

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
    $action = New-ScheduledTaskAction -Execute $ps -Argument ("-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId {0} -ForceNew" -f $MachineId)
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
    $principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force -ErrorAction Stop | Out-Null
    $created = $true
    Write-Host ("INFO Register-ScheduledTask {0} user={1}" -f $TaskName, $RunAsUser)
} catch {
    Write-Host ("WARN Register-ScheduledTask: {0}" -f $_.Exception.Message)
    $create = cmd /c "schtasks /Create /TN `"$TaskName`" /SC ONLOGON /RU `"$RunAsUser`" /RL LIMITED /IT /F /TR $tr"
    Write-Host ("INFO schtasks create {0}: {1}" -f $TaskName, (($create | Out-String).Trim()))
    if ($LASTEXITCODE -eq 0) { $created = $true }
}
if ($RunNow -and -not $RegisterOnly) {
    if ($created -and $SkipTidy) {
        # One-shot interactive task with -SkipTidy (deleting a task does not stop its running process).
        $onceName = "$TaskName-once"
        try {
            $onceArg = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId {0} -ForceNew -SkipTidy" -f $MachineId
            $onceAct = New-ScheduledTaskAction -Execute $ps -Argument $onceArg
            $oncePri = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType Interactive -RunLevel Limited
            Register-ScheduledTask -TaskName $onceName -Action $onceAct -Principal $oncePri -Force | Out-Null
            Start-ScheduledTask -TaskName $onceName
            Write-Host ("INFO started {0} (SkipTidy)" -f $onceName)
            Start-Sleep -Seconds 8
        } catch {
            Write-Host ("WARN one-shot SkipTidy tray start failed: {0}" -f $_.Exception.Message)
        } finally {
            Unregister-ScheduledTask -TaskName $onceName -Confirm:$false -ErrorAction SilentlyContinue
        }
    } elseif ($created) {
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
        $s.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tray`" -InstallRoot `"$InstallRoot`" -MachineId $MachineId -ForceNew"
        $s.WorkingDirectory = $InstallRoot
        $s.Description = 'bob TipForm (interactive)'
        $s.Save()
        Write-Host "INFO Startup shortcut $lnk"
    }
}
$ErrorActionPreference = $prevEap

Write-Host "INFO Start-BobTrayInteractive done user=$RunAsUser machine=$MachineId"

\n