#Requires -Version 5.1
# Bob Systray launcher (Start Menu / Desktop shortcut target).
# t794u: the tray does NOT update anything. Updating is the ircBob service's job (Start-Bob -> Update-BobiverseService / work-tree
# sync). Starting the tray RESTARTS the ircBob service (detached, never waited for), so a tray start also picks up a pending update.
# Prefer tools\_Watch-BobTray-<machineId>.ps1 (sets BOB_MACHINE_ID + IRC home).
# ASCII-only for Windows PowerShell 5.1 UTF-8 no BOM.
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$ForceNew,
    [switch]$SkipUpdate,            # accepted and ignored: older launchers still pass it (the tray has no update logic any more)
    [switch]$SkipServiceRestart,    # tests / service-driven recycles: do not restart ircBob
    [string]$ServiceName = 'ircBob',
    [switch]$SkipTidy,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = Split-Path $PSScriptRoot -Parent }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$tray = Join-Path $RepoRoot 'tools\Watch-BobTray.ps1'
if (-not (Test-Path -LiteralPath $tray)) {
    throw "missing $tray"
}

function Get-BobSystrayMachineId {
    $mid = ([string]$env:BOB_MACHINE_ID).Trim()
    if ($mid) { return $mid.ToLowerInvariant() }
    try {
        Import-Module (Join-Path $RepoRoot 'src\BobBridge.psd1') -Force -ErrorAction SilentlyContinue
        if (Get-Command Get-ThisMachineId -ErrorAction SilentlyContinue) {
            $m = [string](Get-ThisMachineId)
            if ($m) { return $m.ToLowerInvariant() }
        }
    }
    catch { }
    $hn = $env:COMPUTERNAME
    if ($hn -match '(?i)marchhare') { return 'marchhare' }
    if ($hn -match '(?i)flamingo') { return 'flamingo' }
    if ($hn -match '(?i)ce-priority|dev1') { return 'ce-priority-dev1' }
    # #42: any other host = its own lowercased machine name (no hardcoded fleet).
    if ($hn) { return $hn.ToLowerInvariant() }
    return $null
}

function Ensure-BobSystraySeatWrapper {
    param([string]$Root, [string]$MachineId)
    $wrap = Join-Path $Root ("tools\_Watch-BobTray-{0}.ps1" -f $MachineId)
    $ircHome = Join-Path $env:USERPROFILE '.bobiverse'
    $bridge = Join-Path $env:USERPROFILE '.grok\bob-bridge'
    $trayPath = Join-Path $Root 'tools\Watch-BobTray.ps1'
    $lines = @(
        '# DO NOT EDIT - per-machine wrapper from Start-BobFleetTray / Install-BobFleet.'
        '$ErrorActionPreference = "Continue"'
        'Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {'
        '  $_.CommandLine -and [int]$_.ProcessId -ne $PID -and ('
        '    $_.CommandLine -match ''(-File|-f)\s+"?[^"\s]*Watch-BobTray\.ps1'' -or'
        '    $_.CommandLine -match ''(-File|-f)\s+"?[^"\s]*_Watch-BobTray-[^\s"]+\.ps1'''
        '  )'
        '} | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { } }'
        'Start-Sleep -Milliseconds 600'
        ('$env:BOB_IRC_HOME = "{0}"' -f $ircHome.Replace('\', '\\'))
        ('$env:BOB_HOME = "{0}"' -f $ircHome.Replace('\', '\\'))
        ('$env:BOB_MACHINE_ID = "{0}"' -f $MachineId)
        ('$env:BOB_BRIDGE_HOME = "{0}"' -f $bridge.Replace('\', '\\'))
        ('& "{0}"' -f $trayPath)
    )
    $needWrite = $true
    if (Test-Path -LiteralPath $wrap) {
        $cur = Get-Content -LiteralPath $wrap -Raw -ErrorAction SilentlyContinue
        # Rewrite when path/id change OR when the old broad "Watch-BobTray" kill filter is still present.
        if ($cur -and $cur -match [regex]::Escape($trayPath) -and $cur -match [regex]::Escape($MachineId) `
                -and $cur -match '\(-File\|-f\)' -and $cur -notmatch 'CommandLine -match "Watch-BobTray"') {
            $needWrite = $false
        }
    }
    if ($needWrite) {
        [IO.File]::WriteAllLines($wrap, $lines, [Text.UTF8Encoding]::new($false))
    }
    return $wrap
}

function Get-BobSystrayTrayProcesses {
    # Match bare Watch-BobTray.ps1 AND seat wrappers (_Watch-BobTray-marchhare.ps1).
    # Wrapper CommandLine does not contain "Watch-BobTray.ps1", so a strict .ps1
    # suffix miss made ForceNew leave ghosts and "failed to stay up" false-fail.
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'Watch-BobTray\.ps1' -or
                $_.CommandLine -match '_Watch-BobTray-[^\s"]+\.ps1'
            )
        })
}

function Invoke-BobSystrayTidy {
    # CAST IRON (Simon 2026-09-27): start/restart MUST
    # 1) close prior agent sessions (Stop-BobSystrayPriorAgents)
    # 2) tidy leftover session powershell/python/node
    # 3) sweep orphan NotifyIcons (ghost tray icons)
    param([string]$Root)
    $psExe = (Get-Command powershell.exe).Source
    $stopAgents = Join-Path $Root 'tools\Stop-BobSystrayPriorAgents.ps1'
    if (Test-Path -LiteralPath $stopAgents) {
        Write-Output 'tidy: Stop-BobSystrayPriorAgents'
        try {
            & $psExe -NoProfile -ExecutionPolicy Bypass -File $stopAgents 2>&1 | ForEach-Object { Write-Output $_ }
        }
        catch {
            Write-Warning ("tidy prior agents failed: {0}" -f $_.Exception.Message)
        }
    }
    else {
        Write-Warning "tidy: missing $stopAgents"
    }
    $cleanup = Join-Path $Root 'tools\Cleanup-OrphanAgents.ps1'
    if (Test-Path -LiteralPath $cleanup) {
        Write-Output 'tidy: Cleanup-OrphanAgents'
        try {
            & $psExe -NoProfile -ExecutionPolicy Bypass -File $cleanup 2>&1 | ForEach-Object { Write-Output $_ }
        }
        catch {
            Write-Warning ("tidy cleanup failed: {0}" -f $_.Exception.Message)
        }
    }
    else {
        Write-Warning "tidy: missing $cleanup"
    }
    $icons = Join-Path $Root 'tools\Clear-BobOrphanNotifyIcons.ps1'
    if (Test-Path -LiteralPath $icons) {
        Write-Output 'tidy: Clear-BobOrphanNotifyIcons'
        try {
            & $psExe -NoProfile -ExecutionPolicy Bypass -File $icons 2>&1 | ForEach-Object { Write-Output $_ }
        }
        catch {
            Write-Warning ("tidy notify icons failed: {0}" -f $_.Exception.Message)
        }
    }
    else {
        Write-Warning "tidy: missing $icons"
    }
}

$hits = @(Get-BobSystrayTrayProcesses)

if ($ForceNew -and $hits.Count -gt 0) {
    # FR #453: if Restart already announced, outbox is empty; if an external
    # ForceNew kills a live tray, still try a best-effort departure line first.
    try {
        $ircHomeFn = Join-Path $env:USERPROFILE '.bobiverse'
        if (Test-Path -LiteralPath $ircHomeFn) {
            $midFn = Get-BobSystrayMachineId
            if (-not $midFn) { $midFn = 'unknown' }
            $nickFn = 'bob-{0}' -f $midFn
            $msgFn = '{0}: tray Restart - logging off IRC (graceful PART/QUIT)' -f $nickFn
            $lineFn = 'PRIVMSG #bobiverse :{0}' -f $msgFn
            $obFn = Join-Path $ircHomeFn 'outbox.txt'
            $needAnnounce = $true
            if (Test-Path -LiteralPath $obFn) {
                $curOb = ''
                try { $curOb = [IO.File]::ReadAllText($obFn) } catch { }
                if ($curOb -and $curOb.IndexOf('logging off IRC', [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $needAnnounce = $false
                }
            }
            $agentStillUp = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                    $_.CommandLine -and $_.CommandLine -match 'irc_agent\.py' -and $_.CommandLine -match 'bobiverse'
                }).Count -gt 0
            # Skip if Restart already logged out (agent gone) — avoid orphan announce for next join.
            if ($needAnnounce -and $agentStillUp) {
                if (Test-Path -LiteralPath $obFn) {
                    $lenFn = 0
                    try { $lenFn = ([IO.FileInfo]$obFn).Length } catch { }
                    if ($lenFn -gt 0) {
                        $bakFn = Join-Path $ircHomeFn ('outbox.bak-depart-forcenew-{0}.txt' -f [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
                        try { [IO.File]::Copy($obFn, $bakFn, $true) } catch { }
                    }
                }
                [IO.File]::WriteAllText($obFn, $lineFn + "`n", [Text.UTF8Encoding]::new($false))
                Write-Output ('irc departure announce (ForceNew): {0}' -f $msgFn)
                $deadlineFn = [datetime]::UtcNow.AddSeconds(20)
                while ([datetime]::UtcNow -lt $deadlineFn) {
                    if (-not (Test-Path -LiteralPath $obFn)) { break }
                    $rawFn = ''
                    try { $rawFn = [IO.File]::ReadAllText($obFn) } catch { }
                    if ([string]::IsNullOrWhiteSpace($rawFn) -or $rawFn.IndexOf($lineFn, [StringComparison]::Ordinal) -lt 0) { break }
                    Start-Sleep -Milliseconds 250
                }
                Start-Sleep -Seconds 1
            }
        }
    }
    catch {
        Write-Warning ("ForceNew IRC departure announce failed: {0}" -f $_.Exception.Message)
    }
    foreach ($h in $hits) {
        try { Stop-Process -Id ([int]$h.ProcessId) -Force -ErrorAction SilentlyContinue } catch { }
    }
    Start-Sleep -Milliseconds 800
    $hits = @()
}

# Always tidy on start/restart (after ForceNew kill so dead tray is not "kept").
if (-not $SkipTidy -and -not $WhatIf) {
    Invoke-BobSystrayTidy -Root $RepoRoot
    $hits = @(Get-BobSystrayTrayProcesses)
}

if ($hits.Count -gt 0 -and -not $ForceNew) {
    $keep = $hits | Sort-Object CreationDate | Select-Object -First 1
    $flagDir = Join-Path $env:USERPROFILE '.grok\bob-fleet'
    New-Item -ItemType Directory -Force -Path $flagDir | Out-Null
    Set-Content -LiteralPath (Join-Path $flagDir 'show-tip.req') -Value ((Get-Date).ToUniversalTime().ToString('o')) -Encoding utf8
    Write-Output ("Bob Systray already running pid={0}" -f $keep.ProcessId)
    exit 0
}

if ($WhatIf) {
    Write-Output 'would-tidy-and-start-tray'
    exit 0
}

# t794u: starting the systray restarts the service (fire and forget: a detached helper stops, waits for STOPPED, starts).
if (-not $SkipServiceRestart -and ([string]$env:BOBIVERSE_NO_SERVICE_RESTART).Trim() -ne '1') {
    $lifecycle = Join-Path $PSScriptRoot 'BobTrayLifecycle.ps1'
    if (Test-Path -LiteralPath $lifecycle) {
        . $lifecycle
        $svcPid = Restart-BobTrayService -ServiceName $ServiceName -ToolsDir $PSScriptRoot
        Write-Output ('restarting service {0} (detached helper pid={1})' -f $ServiceName, $svcPid)
    }
    else { Write-Warning "missing $lifecycle - ircBob not restarted" }
}

$mid = Get-BobSystrayMachineId
if (-not $mid) {
    Write-Warning 'BOB_MACHINE_ID unresolved - starting Watch-BobTray without seat wrapper'
    $launch = $tray
}
else {
    $env:BOB_MACHINE_ID = $mid
    $launch = Ensure-BobSystraySeatWrapper -Root $RepoRoot -MachineId $mid
    Write-Output ("using seat wrapper {0}" -f $launch)
}

$ps = (Get-Command powershell.exe).Source
# Win32_Process.Create breaks away from agent/console job objects. Start-Process
# -PassThru children die when the launching job closes (Grok Build shells, etc.).
$argLine = '-NoProfile -STA -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $launch
$cmdLine = '"{0}" {1}' -f $ps, $argLine
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine      = $cmdLine
    CurrentDirectory = $RepoRoot
}
$launcherPid = 0
if ($created -and [int]$created.ReturnValue -eq 0 -and $created.ProcessId) {
    $launcherPid = [int]$created.ProcessId
}
else {
    # Fallback for hosts that block WMI process create.
    $proc = Start-Process -FilePath $ps -ArgumentList @(
        '-NoProfile', '-STA', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
        '-File', $launch
    ) -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru
    if ($proc) { $launcherPid = [int]$proc.Id }
}

Start-Sleep -Seconds 2
# Second icon sweep: Explorer drops ghosts from the ForceNew kill once the new tray is up.
if (-not $SkipTidy) {
    $icons = Join-Path $RepoRoot 'tools\Clear-BobOrphanNotifyIcons.ps1'
    if (Test-Path -LiteralPath $icons) {
        try {
            & $ps -NoProfile -ExecutionPolicy Bypass -File $icons | Out-Null
        }
        catch { }
    }
}
$alive = @(Get-BobSystrayTrayProcesses)
if ($alive.Count -eq 0) {
    throw ("Watch-BobTray failed to stay up after start (launcherPid={0} launch={1})" -f $launcherPid, $launch)
}
Write-Output ("Bob Systray started trayPid={0} count={1}" -f $alive[0].ProcessId, $alive.Count)
exit 0
