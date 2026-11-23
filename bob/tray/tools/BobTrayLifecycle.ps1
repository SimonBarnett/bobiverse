#Requires -Version 5.1
# t794u/t798u: tray lifecycle helpers (dot-sourced by Watch-BobTray.ps1 and Start-BobFleetTray.ps1). ASCII-only for PS 5.1.
# The tray never updates anything: the ircBob service (Start-Bob -> Update-BobiverseService / work-tree sync) does the update.

function Test-BobTrayServiceName {
    param([string]$Name)
    return [bool]($Name -match '^[A-Za-z0-9_.-]{1,64}$')
}

function Start-BobTrayDetached {
    # Start a hidden, windowless process and return IMMEDIATELY (fire and forget: never waited for, never read from).
    # -Launcher is for tests; the default is [Diagnostics.Process]::Start with CreateNoWindow.
    param([Parameter(Mandatory)][string]$FilePath, [string]$Arguments = '', [scriptblock]$Launcher = $null)
    if ($Launcher) { return (& $Launcher $FilePath $Arguments) }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $p = [System.Diagnostics.Process]::Start($psi)
    if ($p) { return [int]$p.Id }
    return 0
}

function Stop-BobTrayService {
    # Fire and forget: `sc.exe stop <name>` in its own process. We do not wait for the service to finish stopping.
    param([string]$ServiceName = 'ircBob', [scriptblock]$Launcher = $null)
    if (-not (Test-BobTrayServiceName $ServiceName)) { return 0 }
    $sc = Join-Path $env:SystemRoot 'System32\sc.exe'
    return (Start-BobTrayDetached -FilePath $sc -Arguments ('stop {0}' -f $ServiceName) -Launcher $Launcher)
}

function Restart-BobTrayService {
    # Detached helper (stop, wait for STOPPED, start) so the caller never blocks on the service.
    param([string]$ServiceName = 'ircBob', [string]$ToolsDir = '', [scriptblock]$Launcher = $null)
    if (-not (Test-BobTrayServiceName $ServiceName)) { return 0 }
    if (-not $ToolsDir) { $ToolsDir = $PSScriptRoot }
    $helper = Join-Path $ToolsDir 'Invoke-BobTrayServiceControl.ps1'
    if (-not (Test-Path -LiteralPath $helper) -and -not $Launcher) { return 0 }
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $argLine = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Action Restart -ServiceName {1}' -f $helper, $ServiceName
    return (Start-BobTrayDetached -FilePath $ps -Arguments $argLine -Launcher $Launcher)
}

function Invoke-BobTrayExitSequence {
    <#
      Exit order (t798u / FR #9034): 1 close every dialog and dispose the tray icon IMMEDIATELY,
      2 exit the UI loop. TipForm Exit must NOT stop ircBob (ear is a machine service).
      -StopService is optional for legacy callers; when omitted or $null the step is skipped.
      Each step is isolated: a failing step never skips the next.
      Returns the names of the steps in the order they ran.
    #>
    param(
        [Parameter(Mandatory)][scriptblock]$CloseDialogs,
        [Parameter(Mandatory)][scriptblock]$DisposeIcon,
        [Parameter(Mandatory)][scriptblock]$ExitUi,
        [scriptblock]$StopService = $null
    )
    $ran = New-Object System.Collections.Generic.List[string]
    $steps = @(
        @('close-dialogs', $CloseDialogs),
        @('dispose-icon', $DisposeIcon),
        @('exit-ui', $ExitUi)
    )
    # FR #9034: do not stop ircBob on TipForm Exit; optional legacy StopService only when passed.
    if ($null -ne $StopService) {
        $steps += ,@('stop-service', $StopService)
    }
    foreach ($step in $steps) {
        $ran.Add([string]$step[0])
        try { & $step[1] } catch { }
    }
    return $ran.ToArray()
}

function Get-BobTrayLifecycleDir {
    $dir = Join-Path $env:LOCALAPPDATA 'Bobiverse'
    New-Item -ItemType Directory -Force -Path $dir -ErrorAction SilentlyContinue | Out-Null
    return $dir
}

function Write-BobTrayLifecycleEvent {
    # FR #1636 / #1642: append one JSON line to %LOCALAPPDATA%\Bobiverse\tray-lifecycle.log
    param(
        [Parameter(Mandatory)][string]$Event,
        [hashtable]$Fields = @{}
    )
    try {
        $dir = Get-BobTrayLifecycleDir
        $line = [ordered]@{
            ts    = (Get-Date).ToUniversalTime().ToString('o')
            event = $Event
            pid   = $PID
            user  = $env:USERNAME
        }
        foreach ($k in @($Fields.Keys)) { $line[$k] = $Fields[$k] }
        Add-Content -LiteralPath (Join-Path $dir 'tray-lifecycle.log') -Value (($line | ConvertTo-Json -Compress)) -Encoding utf8
    }
    catch { }
}

function Get-BobTrayWatchdogSuppressPath {
    return (Join-Path (Get-BobTrayLifecycleDir) 'tray-watchdog.suppress')
}

function Set-BobTrayWatchdogSuppress {
    # Intentional TipForm Exit: watchdog must not relaunch until cleared or TTL expires (FR #1642).
    param([string]$Reason = 'Exit', [int]$TtlMinutes = 1440)
    try {
        $path = Get-BobTrayWatchdogSuppressPath
        $doc = @{
            ts           = (Get-Date).ToUniversalTime().ToString('o')
            reason       = $Reason
            pid          = $PID
            ttl_minutes  = $TtlMinutes
            until        = (Get-Date).ToUniversalTime().AddMinutes($TtlMinutes).ToString('o')
        }
        Set-Content -LiteralPath $path -Value ($doc | ConvertTo-Json -Compress) -Encoding utf8
        Write-BobTrayLifecycleEvent -Event 'watchdog-suppress' -Fields @{ reason = $Reason; ttlMinutes = $TtlMinutes }
    }
    catch { }
}

function Clear-BobTrayWatchdogSuppress {
    try {
        $path = Get-BobTrayWatchdogSuppressPath
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            Write-BobTrayLifecycleEvent -Event 'watchdog-suppress-clear' -Fields @{}
        }
    }
    catch { }
}

function Test-BobTrayWatchdogSuppressed {
    param([datetime]$Now = (Get-Date).ToUniversalTime())
    $path = Get-BobTrayWatchdogSuppressPath
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try {
        $raw = Get-Content -LiteralPath $path -Raw -ErrorAction Stop
        $doc = $raw | ConvertFrom-Json
        $until = [datetime]::Parse([string]$doc.until, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
        if ($until.Kind -eq [DateTimeKind]::Unspecified) { $until = [DateTime]::SpecifyKind($until, [DateTimeKind]::Utc) }
        return ($Now -lt $until.ToUniversalTime())
    }
    catch {
        return $true
    }
}

function Test-BobTrayIntentionalExeParkPresent {
    # FR #9199: clickfalse/clicktrue park means TipForm Watch owns the UI.
    # Sync/ForceNew/hotpatch must not leave a live tools\bob-tray.exe beside it.
    # Distinct from bob-tray.exe.clickfix-park (FR #9044 restore-when-missing).
    param([string]$Root)
    if (-not $Root) { return $false }
    $tools = Join-Path $Root 'tools'
    foreach ($leaf in @('bob-tray.exe.clickfalse-park', 'bob-tray.exe.clicktrue-park')) {
        if ([IO.File]::Exists((Join-Path $tools $leaf))) { return $true }
    }
    return $false
}

function Remove-BobTrayLiveExeWhileParked {
    # FR #9199: if intentional park is present and live bob-tray.exe exists, remove the live exe.
    # Keeps the park file. Safe no-op when not parked or live already absent.
    param([string]$Root)
    $out = [pscustomobject]@{ Parked = $false; Removed = $false; Live = $null; Park = $null }
    if (-not $Root) { return $out }
    $tools = Join-Path $Root 'tools'
    $live = Join-Path $tools 'bob-tray.exe'
    $out.Live = $live
    if (-not (Test-BobTrayIntentionalExeParkPresent -Root $Root)) { return $out }
    $out.Parked = $true
    foreach ($leaf in @('bob-tray.exe.clickfalse-park', 'bob-tray.exe.clicktrue-park')) {
        $p = Join-Path $tools $leaf
        if ([IO.File]::Exists($p)) { $out.Park = $p; break }
    }
    if (-not [IO.File]::Exists($live)) { return $out }
    try {
        [IO.File]::Delete($live)
        $out.Removed = -not [IO.File]::Exists($live)
    } catch {
        try {
            Remove-Item -LiteralPath $live -Force -ErrorAction Stop
            $out.Removed = -not [IO.File]::Exists($live)
        } catch {
            $out.Removed = $false
        }
    }
    return $out
}

function Test-BobTrayProcessHasSeatChildren {
    # FR #9205: true when ParentProcessId has a child whose CommandLine looks like a TipForm seat
    # (bob-worker.exe / bob_worker.py / seat-wrapper). Killing that parent drops OpenCode seats.
    param([Parameter(Mandatory)][int]$ParentProcessId)
    if ($ParentProcessId -le 0) { return $false }
    try {
        $kids = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
                [int]$_.ParentProcessId -eq $ParentProcessId -and $_.CommandLine -and (
                    $_.CommandLine -match '(?i)bob-worker\.exe' -or
                    $_.CommandLine -match '(?i)bob_worker\.py' -or
                    $_.CommandLine -match '(?i)seat-wrapper' -or
                    $_.CommandLine -match '(?i)opencode.*seat' -or
                    ($_.Name -match '(?i)^bob-worker')
                )
            })
        return ($kids.Count -gt 0)
    } catch {
        return $false
    }
}

function Stop-BobTrayProcessesProtectingSeats {
    # FR #9205: stop bob-tray.exe processes only when they do not parent live TipForm seats.
    # Prefer file-delete of staged exe (Remove-BobTrayLiveExeWhileParked) over kill while seats run.
    param([string]$Root = '')
    $out = [pscustomobject]@{ Killed = 0; SkippedForSeats = 0; Examined = 0 }
    $procs = @()
    try { $procs = @(Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue) } catch { $procs = @() }
    foreach ($pr in $procs) {
        $out.Examined++
        # Never assign $pid / $PID --- automatic read-only in WinPS 5.1 (MRB #9206 FAIL).
        $trayPid = 0
        try { $trayPid = [int]$pr.Id } catch { continue }
        if ($trayPid -le 0) { continue }
        if (Test-BobTrayProcessHasSeatChildren -ParentProcessId $trayPid) {
            $out.SkippedForSeats++
            continue
        }
        try {
            Stop-Process -Id $trayPid -Force -ErrorAction SilentlyContinue
            $out.Killed++
        } catch { }
    }
    return $out
}

function Restore-BobTrayExeFromClickfixPark {
    # FR #9044: tools\bob-tray.exe missing while tools\bob-tray.exe.clickfix-park remains.
    # Test-Path is falsely False on that dotted name. File.Copy restores the live exe and keeps the park.
    # FR #9199: never restore (or keep) live when clickfalse/clicktrue intentional park is present.
    param([string]$Root)
    if (-not $Root) { return $null }
    $tools = Join-Path $Root 'tools'
    $live = Join-Path $tools 'bob-tray.exe'
    $park = Join-Path $tools 'bob-tray.exe.clickfix-park'
    if (Test-BobTrayIntentionalExeParkPresent -Root $Root) {
        [void](Remove-BobTrayLiveExeWhileParked -Root $Root)
        return $null
    }
    if ([IO.File]::Exists($live)) { return $live }
    if (-not [IO.File]::Exists($park)) { return $null }
    try {
        [IO.File]::Copy($park, $live, $false)
    } catch {
        return $null
    }
    if ([IO.File]::Exists($live) -and [IO.File]::Exists($park)) { return $live }
    return $null
}

function Test-BobTrayProcessPresent {
    # True when bob-tray.exe or Watch-BobTray / seat-wrapper is alive (FR #1642 watchdog).
    # FR #2585: Name -eq bob-tray.exe is enough (ExecutablePath may be null); already-running
    # duplicate exits must not look like a missing tray to the watchdog.
    # FR #3909: Get-Process bob-tray first — Win32_Process CIM can take ~1 minute on a busy box
    # and made the Interactive BobiverseTrayWatchdog host look hung (blank console steal focus).
    param([string]$InstallRoot = '')
    if (@(Get-Process -Name 'bob-tray' -ErrorAction SilentlyContinue).Count -gt 0) { return $true }
    $root = [string]$InstallRoot
    if (-not $root) { $root = [string]$env:BOB_AI_ROOT }
    $toolsPrefix = ''
    if ($root) {
        $bobRoot = if ((Split-Path -Leaf $root) -ieq 'bob') { $root } else { Join-Path $root 'bob' }
        try { $toolsPrefix = [IO.Path]::GetFullPath((Join-Path $bobRoot 'tools')) } catch { $toolsPrefix = Join-Path $bobRoot 'tools' }
    }
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            ($_.CommandLine -and (
                $_.CommandLine -match 'Watch-BobTray\.ps1' -or
                $_.CommandLine -match '_Watch-BobTray-[^\s"]+\.ps1' -or
                $_.CommandLine -match '(?i)bob-tray\.exe'
            )) -or (
                $_.Name -eq 'bob-tray.exe' -and (
                    -not $toolsPrefix -or
                    -not $_.ExecutablePath -or
                    $_.ExecutablePath.StartsWith($toolsPrefix, [StringComparison]::OrdinalIgnoreCase)
                )
            )
        })
    return ($hits.Count -gt 0)
}