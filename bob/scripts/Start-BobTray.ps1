#Requires -Version 5.1
<#
.SYNOPSIS
  Public launcher for the TipForm Bob systray shipped in the bob MSI.
.DESCRIPTION
  Sets BOB_MACHINE_ID / BOB_BRIDGE_HOME / IRC home, then starts tools\Watch-BobTray.ps1
  under InstallRoot (STA). Companion to the ircBob Windows service --- not a BobFleet task.
.NOTES
  t794u: the tray never updates. Product Sync/ff and the release self-update run only on ircBob service start (Start-Bob).
  Starting the tray (this launcher, the 'Start Systray' shortcut, logon autostart) restarts ircBob via
  Start-BobFleetTray, so a start also applies a pending update. TipForm Exit never stops ircBob
  (FR #9034 / #9146; ear is a machine service). Under #9011 park, Exit uses a 5m watchdog suppress.
  FR #1636: autostart/shortcuts pass -SkipTidy (ForceNew replaces the prior tray only). TipForm Restart
  still tidies seats. FR #9509: prior sweep uses timed Win32_Process + Get-Process bob-tray fallback (no bare CIM hang). Lifecycle lines append to %LOCALAPPDATA%\Bobiverse\tray-lifecycle.log.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',   # '' = installed root / discovered <ai root>\bob (t780u)
    [string]$ServiceName = 'ircBob',
    [string]$BobHome = '',
    [string]$MachineId = '',
    [switch]$ForceNew,
    # #32 / FR #1636: do not run Stop-BobSystrayPriorAgents (kills grok.exe seats, Grok Bot, Watch-AgentHealth).
    # Also honoured via env BOBIVERSE_NO_TIDY=1 (set by Install-Bob for quiet/MSI installs).
    [switch]$SkipTidy,
    # FR #3987: Install-Bob / MSI CA owns Start-Service ircBob; do not Restart-BobTrayService from the tray child.
    # Also honoured via env BOBIVERSE_NO_SERVICE_RESTART=1.
    [switch]$SkipServiceRestart
)

$ErrorActionPreference = 'Continue'
# FR #1636 / #1642: shared lifecycle writer lives in tools\BobTrayLifecycle.ps1 when composed.
$__life = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\BobTrayLifecycle.ps1'
if (-not (Test-Path -LiteralPath $__life)) { $__life = Join-Path $PSScriptRoot '..\tray\tools\BobTrayLifecycle.ps1' }
if (Test-Path -LiteralPath $__life) { . $__life }
if (-not (Get-Command Write-BobTrayLifecycleEvent -ErrorAction SilentlyContinue)) {
    function Write-BobTrayLifecycleEvent {
        param([string]$Event, [hashtable]$Fields = @{})
        try {
            $dir = Join-Path $env:LOCALAPPDATA 'Bobiverse'
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $line = [ordered]@{
                ts    = (Get-Date).ToUniversalTime().ToString('o')
                event = $Event
                pid   = $PID
                user  = $env:USERNAME
            }
            foreach ($k in $Fields.Keys) { $line[$k] = $Fields[$k] }
            Add-Content -LiteralPath (Join-Path $dir 'tray-lifecycle.log') -Value (($line | ConvertTo-Json -Compress)) -Encoding utf8
        } catch { }
    }
}
# Back-compat alias used by FR #1636 Start-BobTray body.
function Write-BobTrayLifecycle { param([string]$Event, [hashtable]$Fields = @{}); Write-BobTrayLifecycleEvent -Event $Event -Fields $Fields }

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
# The tray (vendored Watch-BobTray.ps1) resolves sibling products through BOB_AI_ROOT instead of a baked-in C:\ai.
if (-not $env:BOB_AI_ROOT -and (Split-Path -Leaf $InstallRoot) -ieq 'bob') { $env:BOB_AI_ROOT = Split-Path -Parent $InstallRoot }

$tray = Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'
if (-not (Test-Path -LiteralPath $tray)) {
    # Dev fallback: vendored tree next to scripts\
    $repo = Split-Path -Parent $PSScriptRoot
    $trayDir = Join-Path $repo 'third_party\bob-tray'
    foreach ($cand in @((Join-Path $repo 'tray'), (Join-Path (Split-Path -Parent $repo) 'bob\tray'), $trayDir)) {   # t829u: bob\tray is the first-class source
        if (Test-Path -LiteralPath (Join-Path $cand 'tools\Watch-BobTray.ps1')) { $trayDir = $cand; break }
    }
    $alt = Join-Path $trayDir 'tools\Watch-BobTray.ps1'
    if (Test-Path -LiteralPath $alt) {
        $InstallRoot = [IO.Path]::GetFullPath($trayDir)
        $tray = Join-Path $InstallRoot 'tools\Watch-BobTray.ps1'
    }
}
if (-not (Test-Path -LiteralPath $tray)) {
    Write-Error "missing TipForm tray: $InstallRoot\tools\Watch-BobTray.ps1 (sync/pack bob)"
    exit 1
}

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
} else {
    $MachineId = ($MachineId -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}

if (-not $BobHome) {
    $BobHome = Join-Path $env:USERPROFILE '.bobiverse'
}
$bridge = Join-Path $env:USERPROFILE '.grok\bob-bridge'
New-Item -ItemType Directory -Force -Path $BobHome, $bridge | Out-Null

$env:BOB_MACHINE_ID = $MachineId
$env:BOB_BRIDGE_HOME = $bridge
$env:BOB_IRC_HOME = $BobHome
$env:BOB_HOME = $BobHome
if (-not $env:BOBIVERSE_BOB_VERSION) {
    foreach ($vf in @(
            (Join-Path $InstallRoot 'VERSION'),
            (Join-Path (Split-Path -Parent $PSScriptRoot) 'src\VERSION'),
            (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'common\VERSION')   # t773u split repo
        )) {
        if ($vf -and (Test-Path -LiteralPath $vf)) {
            $env:BOBIVERSE_BOB_VERSION = ([string](Get-Content -LiteralPath $vf -TotalCount 1)).Trim()
            break
        }
    }
}

# One TipForm only: stop other Watch-BobTray / seat wrappers (and legacy minimal Start-BobTray hosts).
# FR #9509: never bare Get-CimInstance Win32_Process here — hung CIM stalls ForceNew with no bob-tray.exe.
if (-not (Get-Command Get-BobTrayPriorProcessHits -ErrorAction SilentlyContinue)) {
    # Lifecycle may be missing in sparse trees; define a minimal timed+fallback copy.
    function Get-BobTrayPriorProcessHits {
        param([int]$TimeoutSec = 8, [int]$ExcludePid = 0, [string]$InstallRoot = '')
        if ($ExcludePid -le 0) { $ExcludePid = $PID }
        $hits = New-Object System.Collections.Generic.List[object]
        try {
            $scope = New-Object System.Management.ManagementScope
            $query = New-Object System.Management.ObjectQuery 'SELECT ProcessId, Name, CommandLine, ExecutablePath FROM Win32_Process'
            $opt = New-Object System.Management.EnumerationOptions
            $opt.Timeout = [TimeSpan]::FromSeconds([Math]::Max(1, $TimeoutSec))
            $opt.ReturnImmediately = $false
            $searcher = New-Object System.Management.ManagementObjectSearcher($scope, $query, $opt)
            foreach ($mo in @($searcher.Get())) {
                $procId = 0
                try { $procId = [int]$mo['ProcessId'] } catch { continue }
                if ($procId -eq $ExcludePid) { continue }
                $cmd = [string]$mo['CommandLine']
                $name = [string]$mo['Name']
                if ($cmd -and (
                        $cmd -match 'Watch-BobTray\.ps1' -or
                        $cmd -match '_Watch-BobTray-[^\s"]+\.ps1' -or
                        ($cmd -match 'Start-BobTray\.ps1' -and $cmd -notmatch [regex]::Escape($MyInvocation.MyCommand.Path)) -or
                        ($cmd -match '(?i)bob-tray\.exe')
                    ) -or ($name -eq 'bob-tray.exe')) {
                    $hits.Add([pscustomobject]@{ ProcessId = $procId; Name = $name; Source = 'wmi-timed' })
                }
            }
        } catch { }
        if ($hits.Count -eq 0) {
            try {
                foreach ($p in @(Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue)) {
                    if ([int]$p.Id -eq $ExcludePid) { continue }
                    $hits.Add([pscustomobject]@{ ProcessId = [int]$p.Id; Name = 'bob-tray.exe'; Source = 'get-process' })
                }
            } catch { }
        }
        return @($hits.ToArray())
    }
}
$prior = @(Get-BobTrayPriorProcessHits -TimeoutSec 8 -ExcludePid $PID -InstallRoot $InstallRoot | Where-Object {
        # Keep Start-BobTray self out even when CommandLine matched loosely.
        -not ($_.CommandLine -and $_.CommandLine -match 'Start-BobTray\.ps1' -and $_.CommandLine -match [regex]::Escape($MyInvocation.MyCommand.Path))
    })
if ($ForceNew -or $prior.Count -gt 0) {
    foreach ($p in $prior) {
        try {
            Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
            Write-Host ("INFO stopped prior tray pid={0} source={1}" -f $p.ProcessId, $(if ($p.Source) { $p.Source } else { 'n/a' }))
        } catch { }
    }
    Start-Sleep -Milliseconds 600
}

# Prefer Start-BobFleetTray when present (tidy + ircBob restart); else Watch-BobTray direct.
$fleetStart = Join-Path $InstallRoot 'tools\Start-BobFleetTray.ps1'
# FR #1642: a fresh start re-arms the unexpected-exit watchdog.
if (Get-Command Clear-BobTrayWatchdogSuppress -ErrorAction SilentlyContinue) { Clear-BobTrayWatchdogSuppress }
if (Test-Path -LiteralPath $fleetStart) {
    $noTidy = $SkipTidy.IsPresent -or ([string]$env:BOBIVERSE_NO_TIDY).Trim() -eq '1'
    $noSvcRestart = $SkipServiceRestart.IsPresent -or ([string]$env:BOBIVERSE_NO_SERVICE_RESTART).Trim() -eq '1'
    if ($noTidy) { Write-Host 'INFO tray start: SkipTidy (seats and Grok Bot are left running)' }
    if ($noSvcRestart) { Write-Host 'INFO tray start: SkipServiceRestart (FR #3987; caller owns ircBob start)' }
    Write-BobTrayLifecycle -Event 'start' -Fields @{
        installRoot = $InstallRoot
        machineId   = $MachineId
        forceNew    = [bool]$ForceNew
        skipTidy    = [bool]$noTidy
        skipServiceRestart = [bool]$noSvcRestart
        via         = 'Start-BobFleetTray'
    }
    & $fleetStart -RepoRoot $InstallRoot -ForceNew:$ForceNew -SkipTidy:$noTidy -SkipServiceRestart:$noSvcRestart
    $code = $LASTEXITCODE
    Write-BobTrayLifecycle -Event 'start-exit' -Fields @{ exitCode = $code; skipTidy = [bool]$noTidy; skipServiceRestart = [bool]$noSvcRestart }
    exit $code
}

Write-BobTrayLifecycle -Event 'start' -Fields @{
    installRoot = $InstallRoot
    machineId   = $MachineId
    forceNew    = [bool]$ForceNew
    skipTidy    = [bool]$SkipTidy
    via         = 'Watch-BobTray-direct'
}
& $tray -RepoRoot $InstallRoot
$code = $LASTEXITCODE
Write-BobTrayLifecycle -Event 'start-exit' -Fields @{ exitCode = $code }
exit $code
