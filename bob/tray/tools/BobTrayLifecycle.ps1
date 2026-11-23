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

function Test-BobTrayExeParked {
    # FR #9011 / #9146: bob-tray.exe renamed aside while Watch TipForm owns the icon
    # (clickfix-park / clickfalse-park / clicktrue-park). TipForm Exit under park must
    # use a short watchdog suppress so Watch can recover TipForm within minutes.
    param([string]$Root)
    if (-not $Root) { return $false }
    $tools = Join-Path $Root 'tools'
    foreach ($name in @('bob-tray.exe.clickfix-park', 'bob-tray.exe.clickfalse-park', 'bob-tray.exe.clicktrue-park')) {
        if ([IO.File]::Exists((Join-Path $tools $name))) { return $true }
    }
    return $false
}
function Restore-BobTrayExeFromClickfixPark {
    # FR #9044: tools\bob-tray.exe missing while tools\bob-tray.exe.clickfix-park remains.
    # Test-Path is falsely False on that dotted name. File.Copy restores the live exe and keeps the park.
    param([string]$Root)
    if (-not $Root) { return $null }
    $tools = Join-Path $Root 'tools'
    $live = Join-Path $tools 'bob-tray.exe'
    $park = Join-Path $tools 'bob-tray.exe.clickfix-park'
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