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
      Exit order (t798u): 1 close every dialog and dispose the tray icon IMMEDIATELY, 2 exit the UI loop,
      3 only then start the service stop, detached. Each step is isolated: a failing step never skips the next.
      Returns the names of the steps in the order they ran.
    #>
    param(
        [Parameter(Mandatory)][scriptblock]$CloseDialogs,
        [Parameter(Mandatory)][scriptblock]$DisposeIcon,
        [Parameter(Mandatory)][scriptblock]$ExitUi,
        [Parameter(Mandatory)][scriptblock]$StopService
    )
    $ran = New-Object System.Collections.Generic.List[string]
    foreach ($step in @(@('close-dialogs', $CloseDialogs), @('dispose-icon', $DisposeIcon), @('exit-ui', $ExitUi), @('stop-service', $StopService))) {
        $ran.Add([string]$step[0])
        try { & $step[1] } catch { }
    }
    return $ran.ToArray()
}