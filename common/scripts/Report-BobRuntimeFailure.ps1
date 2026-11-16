# FR #5050: report a caught tray/ear/Jeeves failure to bobiverse intake (deduped).
# Never throws. Prefer common/scripts/runtime_failure.py; fall back to Report-BobiverseIntakeIssue.

function Report-BobRuntimeFailure {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Component,
        [Parameter(Mandatory)]$Exception,
        [string]$Site = 'caught',
        [string]$Repo = 'SimonBarnett/bobiverse'
    )
    $msg = ''
    if ($Exception -is [System.Exception]) { $msg = [string]$Exception.Message }
    elseif ($Exception -is [System.Management.Automation.ErrorRecord]) { $msg = [string]$Exception.Exception.Message }
    else { $msg = [string]$Exception }
    if (-not $msg) { $msg = '(no message)' }
    # FR #7838: a quoted .NET message ("There is not enough space...") was split by
    # native argv quoting, so site became the next word ("is") and the issue title
    # lost the real error. Pass the text in the environment, never on the command line.
    $inner = $null
    if ($Exception -is [System.Management.Automation.ErrorRecord] -and $Exception.Exception.InnerException) {
        $inner = [string]$Exception.Exception.InnerException.Message
    }
    elseif ($Exception -is [System.Exception] -and $Exception.InnerException) {
        $inner = [string]$Exception.InnerException.Message
    }
    if ($inner -and $msg -notlike ('*' + $inner + '*')) {
        $msg = $msg + ' | ' + $inner
    }
    $here = $PSScriptRoot
    $py = Join-Path $here 'runtime_failure.py'
    $python = $null
    foreach ($c in @('python', 'py')) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { $python = $cmd.Source; break }
    }
    if ($python -and (Test-Path -LiteralPath $py)) {
        $code = @(
            'import os, sys'
            'sys.path.insert(0, r"""' + $here + '""")'
            'import runtime_failure'
            'r = runtime_failure.report_message(os.environ.get("BOB_RF_COMPONENT") or "unknown", os.environ.get("BOB_RF_MESSAGE") or "", site=os.environ.get("BOB_RF_SITE") or "caught")'
            'print(r.get("deduped"), r.get("sig"), r.get("ok"))'
        ) -join '; '
        $prevC = $env:BOB_RF_COMPONENT
        $prevM = $env:BOB_RF_MESSAGE
        $prevS = $env:BOB_RF_SITE
        try {
            $env:BOB_RF_COMPONENT = $Component
            $env:BOB_RF_MESSAGE = $msg
            $env:BOB_RF_SITE = $Site
            $out = & $python -c $code 2>&1
            return [pscustomobject]@{ ok = $true; via = 'runtime_failure'; output = [string]$out }
        }
        catch {
            # fall through to intake script
        }
        finally {
            if ($null -eq $prevC) { Remove-Item Env:BOB_RF_COMPONENT -ErrorAction SilentlyContinue } else { $env:BOB_RF_COMPONENT = $prevC }
            if ($null -eq $prevM) { Remove-Item Env:BOB_RF_MESSAGE -ErrorAction SilentlyContinue } else { $env:BOB_RF_MESSAGE = $prevM }
            if ($null -eq $prevS) { Remove-Item Env:BOB_RF_SITE -ErrorAction SilentlyContinue } else { $env:BOB_RF_SITE = $prevS }
        }
    }
    $intake = Join-Path $here 'Report-BobiverseIntakeIssue.ps1'
    if (-not (Test-Path -LiteralPath $intake)) {
        $intake = Join-Path (Split-Path $here -Parent) 'scripts\Report-BobiverseIntakeIssue.ps1'
    }
    if (Test-Path -LiteralPath $intake) {
        try {
            & $intake -Repo $Repo -Kind issue -Title ("fail: {0} {1}" -f $Component, $Site) -Body ("component={0}`nsite={1}`nerror={2}`nFR #5050" -f $Component, $Site, $msg)
            return [pscustomobject]@{ ok = $true; via = 'intake' }
        }
        catch {
            return [pscustomobject]@{ ok = $false; via = 'intake'; error = $_.Exception.Message }
        }
    }
    return [pscustomobject]@{ ok = $false; via = 'none'; error = 'no reporter' }
}
