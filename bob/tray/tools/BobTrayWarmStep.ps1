# FR #7660: one runspace for stall-alerts and update-hover-engine.
# A fresh Start-Job plus Import-Module on every poll blew the 45s step budget.
# BobBridge is imported once. Later steps pay only the command itself.
# FR #8518: never call PowerShell.Stop() on the poll/UI thread after a timeout —
# a hung WMI/HTTP invoke makes Stop block forever (step-start, no step-timeout).

function Stop-BobTrayWarmEngineShellAsync {
    <#
      FR #8518: fire-and-forget Stop/Dispose so the caller returns within the WaitOne budget.
    #>
    param($Shell)
    if (-not $Shell) { return }
    try {
        $killer = [powershell]::Create()
        [void]$killer.AddScript(@'
param($p)
try { $p.Stop() } catch { }
try { if ($p.Runspace) { $p.Runspace.Close() } } catch { }
try { if ($p.Runspace) { $p.Runspace.Dispose() } } catch { }
try { $p.Dispose() } catch { }
'@).AddArgument($Shell)
        [void]$killer.BeginInvoke()
    } catch { }
}

function Get-BobTrayWarmEngineShell {
    param(
        [string]$Root,
        [int]$ImportTimeoutSec = 15
    )
    $rootKey = [string]$Root
    if ($script:BobTrayWarmShell) {
        $open = $false
        try { $open = $script:BobTrayWarmShell.Runspace.RunspaceStateInfo.State -eq 'Opened' } catch { $open = $false }
        if ($open -and $script:BobTrayWarmRoot -eq $rootKey) { return $script:BobTrayWarmShell }
        # Prior shell is dead or rooted elsewhere — abandon without sync Stop (FR #8518).
        $old = $script:BobTrayWarmShell
        $script:BobTrayWarmShell = $null
        Stop-BobTrayWarmEngineShellAsync -Shell $old
    }
    $rs = [runspacefactory]::CreateRunspace()
    $rs.Open()
    $ps = [powershell]::Create()
    $ps.Runspace = $rs
    $script:BobTrayWarmShell = $ps
    $script:BobTrayWarmRoot = $rootKey
    $psd1 = Join-Path $rootKey 'src\BobBridge.psd1'
    if (Test-Path -LiteralPath $psd1) {
        $ps.Commands.Clear()
        [void]$ps.AddScript('param($Path) Import-Module -Name $Path').AddArgument($psd1)
        # FR #8518: Import-Module can hang; do not use sync Invoke() on the poll thread.
        $importTimeoutSec = [Math]::Max(1, [int]$ImportTimeoutSec)
        $ia = $ps.BeginInvoke()
        if (-not $ia.AsyncWaitHandle.WaitOne($importTimeoutSec * 1000)) {
            $script:BobTrayWarmShell = $null
            Stop-BobTrayWarmEngineShellAsync -Shell $ps
            throw ('warm-shell-import-timeout sec={0}' -f $importTimeoutSec)
        }
        [void]$ps.EndInvoke($ia)
        $ps.Commands.Clear()
        foreach ($streamName in @('Error', 'Warning', 'Information', 'Verbose', 'Debug')) {
            try { $ps.Streams.$streamName.Clear() } catch { }
        }
    }
    return $ps
}

function Invoke-BobTrayWarmEngineStep {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Body,
        [int]$TimeoutSec = -1,
        [string]$Root,
        [object[]]$ArgumentList
    )
    $root = if ($Root) { $Root } else { $script:RepoRoot }
    if ($TimeoutSec -lt 0) {
        if ($script:BobTrayEngineStepTimeoutSec) { $TimeoutSec = [int]$script:BobTrayEngineStepTimeoutSec } else { $TimeoutSec = 45 }
    }
    if ($TimeoutSec -lt 1) { $TimeoutSec = 1 }
    if (Get-Command Write-BobTrayEngineCycleLog -ErrorAction SilentlyContinue) {
        Write-BobTrayEngineCycleLog -Root $root -Message ('step-start name={0}' -f $Name)
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $ps = $null
    try {
        $ps = Get-BobTrayWarmEngineShell -Root $root
    } catch {
        $sw.Stop()
        $err = $_.Exception
        if (Get-Command Write-BobTrayEngineCycleLog -ErrorAction SilentlyContinue) {
            Write-BobTrayEngineCycleLog -Root $root -Message ('step-error name={0} sec={1:n2} err={2}' -f $Name, $sw.Elapsed.TotalSeconds, $err.Message)
        }
        return @{ ok = $false; timedOut = $false; name = $Name; seconds = $sw.Elapsed.TotalSeconds; error = $err; output = $null }
    }
    $ps.Commands.Clear()
    # FR #7697: a reused runspace keeps the last step's error records. A later
    # step then fails with that old message even when its own command succeeded.
    foreach ($streamName in @('Error', 'Warning', 'Information', 'Verbose', 'Debug')) {
        try { $ps.Streams.$streamName.Clear() } catch { }
    }
    $sb = [scriptblock]::Create($Body.ToString())
    [void]$ps.AddScript($sb)
    foreach ($a in @($ArgumentList)) { [void]$ps.AddArgument($a) }
    $async = $null
    $timedOut = $false
    $failed = $null
    $output = $null
    try {
        $async = $ps.BeginInvoke()
        if (-not $async.AsyncWaitHandle.WaitOne([int]$TimeoutSec * 1000)) {
            $timedOut = $true
            # FR #8518: abandon the warm shell. Sync Stop() can hang forever on native WMI/HTTP
            # and leave tray-engine-cycle.log at step-start with no step-timeout / step-end.
            $script:BobTrayWarmShell = $null
            Stop-BobTrayWarmEngineShellAsync -Shell $ps
            $ps = $null
        } else {
            $output = $ps.EndInvoke($async)
            if ($ps.Streams.Error.Count -gt 0) {
                $failed = $ps.Streams.Error[0].Exception
                if (-not $failed) { $failed = New-Object System.Exception ([string]$ps.Streams.Error[0]) }
            }
            $ps.Commands.Clear()
        }
    } catch {
        $failed = $_.Exception
        $orphan = $ps
        $script:BobTrayWarmShell = $null
        $ps = $null
        Stop-BobTrayWarmEngineShellAsync -Shell $orphan
    }
    $sw.Stop()
    if ($timedOut) {
        if (Get-Command Write-BobTrayEngineCycleLog -ErrorAction SilentlyContinue) {
            Write-BobTrayEngineCycleLog -Root $root -Message ('step-timeout name={0} sec={1:n2} limit={2}' -f $Name, $sw.Elapsed.TotalSeconds, $TimeoutSec)
        }
        if (Get-Command Invoke-BobTrayEngineReportTimeout -ErrorAction SilentlyContinue) {
            Invoke-BobTrayEngineReportTimeout -StepName $Name -TimeoutSec $TimeoutSec -Root $root
        }
        return @{ ok = $false; timedOut = $true; name = $Name; seconds = $sw.Elapsed.TotalSeconds; output = $null }
    }
    if ($failed) {
        if (Get-Command Write-BobTrayEngineCycleLog -ErrorAction SilentlyContinue) {
            Write-BobTrayEngineCycleLog -Root $root -Message ('step-error name={0} sec={1:n2} err={2}' -f $Name, $sw.Elapsed.TotalSeconds, $failed.Message)
        }
        return @{ ok = $false; timedOut = $false; name = $Name; seconds = $sw.Elapsed.TotalSeconds; error = $failed; output = $null }
    }
    if (Get-Command Write-BobTrayEngineCycleLog -ErrorAction SilentlyContinue) {
        Write-BobTrayEngineCycleLog -Root $root -Message ('step-end name={0} sec={1:n2}' -f $Name, $sw.Elapsed.TotalSeconds)
    }
    return @{ ok = $true; timedOut = $false; name = $Name; seconds = $sw.Elapsed.TotalSeconds; output = $output }
}
