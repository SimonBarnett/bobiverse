# FR #7660: one runspace for stall-alerts and update-hover-engine.
# A fresh Start-Job plus Import-Module on every poll blew the 45s step budget.
# BobBridge is imported once. Later steps pay only the command itself.

function Get-BobTrayWarmEngineShell {
    param([string]$Root)
    $rootKey = [string]$Root
    if ($script:BobTrayWarmShell) {
        $open = $false
        try { $open = $script:BobTrayWarmShell.Runspace.RunspaceStateInfo.State -eq 'Opened' } catch { $open = $false }
        if ($open -and $script:BobTrayWarmRoot -eq $rootKey) { return $script:BobTrayWarmShell }
        try { $script:BobTrayWarmShell.Dispose() } catch { }
        $script:BobTrayWarmShell = $null
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
        [void]$ps.Invoke()
        $ps.Commands.Clear()
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
    $ps = Get-BobTrayWarmEngineShell -Root $root
    $ps.Commands.Clear()
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
            try { $ps.Stop() } catch { }
            try { $ps.Dispose() } catch { }
            $script:BobTrayWarmShell = $null
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
        try { $ps.Dispose() } catch { }
        $script:BobTrayWarmShell = $null
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
