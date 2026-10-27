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
    $here = $PSScriptRoot
    $py = Join-Path $here 'runtime_failure.py'
    $python = $null
    foreach ($c in @('python', 'py')) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { $python = $cmd.Source; break }
    }
    if ($python -and (Test-Path -LiteralPath $py)) {
        $code = @(
            'import sys'
            'sys.path.insert(0, r"""' + $here + '""")'
            'import runtime_failure'
            'r = runtime_failure.report_message(sys.argv[1], sys.argv[2], site=sys.argv[3])'
            'print(r.get("deduped"), r.get("sig"), r.get("ok"))'
        ) -join '; '
        try {
            $out = & $python -c $code $Component $msg $Site 2>&1
            return [pscustomobject]@{ ok = $true; via = 'runtime_failure'; output = [string]$out }
        }
        catch {
            # fall through to intake script
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
