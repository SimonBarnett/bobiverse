# FR #5052: must-report operational failures (timers, webhooks, IRC posts, heartbeat).
# Best-effort empty catches (Dispose, Hide, Parse/ToInt, timer Stop/Start, CIM list)
# stay silent. This helper never throws.

function Invoke-BobMustReportFailure {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Component,
        [Parameter(Mandatory)][string]$Site,
        $Exception
    )
    try {
        if (-not (Get-Command Report-BobRuntimeFailure -ErrorAction SilentlyContinue)) {
            $rfRoots = @()
            if ($Event -and $Event.MessageData -and $Event.MessageData.Root) {
                $rfRoots += [string]$Event.MessageData.Root
            }
            $rfRoots += (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent)
            foreach ($r in $rfRoots) {
                if (-not $r) { continue }
                foreach ($rel in @('common\scripts\Report-BobRuntimeFailure.ps1', 'scripts\Report-BobRuntimeFailure.ps1')) {
                    $rf = Join-Path $r $rel
                    if (Test-Path -LiteralPath $rf) { . $rf; break }
                }
                if (Get-Command Report-BobRuntimeFailure -ErrorAction SilentlyContinue) { break }
            }
        }
        if (Get-Command Report-BobRuntimeFailure -ErrorAction SilentlyContinue) {
            Report-BobRuntimeFailure -Component $Component -Site $Site -Exception $Exception | Out-Null
            return
        }
        if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
            Report-BobDeterministicException -Site $Site -Exception $Exception | Out-Null
            return
        }
        $root = $null
        if ($Event -and $Event.MessageData -and $Event.MessageData.Root) {
            $root = [string]$Event.MessageData.Root
        }
        if ($root) {
            $logDir = Join-Path $root 'logs'
            if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
            Add-Content -LiteralPath (Join-Path $logDir 'tray-lifecycle.log') `
                -Value ('{0} WARN FR #5052 {1} {2}: {3}' -f [datetime]::UtcNow.ToString('o'), $Component, $Site, [string]$Exception) `
                -Encoding utf8
        }
    }
    catch {
        # BEST_EFFORT: reporter itself must not break the timer tick.
    }
}
