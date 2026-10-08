#Requires -Version 5.1
<#
.SYNOPSIS
  Retire the BobAutoFocus scheduled task and ops auto-focus.py (FR #3190).

.DESCRIPTION
  The interim t846u / #628 BobAutoFocus task ran C:\ai\ops\auto-focus.py every 2 minutes and
  appended per-item !focus lines through the bob ear. Per-repo !focus (FR #1520) makes that
  useless and noisy. This script disables + unregisters the task and renames the ops script
  aside so upgrades cannot revive it. Safe to run when the task is already missing.

.PARAMETER OpsRoot
  Folder that may hold auto-focus.py (default: <ai root>\ops or C:\ai\ops).

.PARAMETER Quiet
  Suppress non-error output (used from Update-BobiverseService post-upgrade).

.PARAMETER WhatIf
  Report actions without changing the machine.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$OpsRoot = '',
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
function Write-Retire([string]$Msg) {
    if (-not $Quiet) { Write-Output $Msg }
}

$taskName = 'BobAutoFocus'
$tq = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($tq) {
    if ($PSCmdlet.ShouldProcess($taskName, 'Disable and Unregister-ScheduledTask')) {
        try { Disable-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null } catch { }
        try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch { }
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Retire "FR #3190 unregistered scheduled task $taskName"
    }
} else {
    Write-Retire "FR #3190 scheduled task $taskName already absent"
}

if (-not $OpsRoot) {
    # FR #3396: never hard-code C:\ai - discover via BOB_AI_ROOT / Get-BobiverseAiRoot.
    if ($env:BOB_AI_ROOT -and (Test-Path -LiteralPath (Join-Path $env:BOB_AI_ROOT 'ops'))) {
        $OpsRoot = Join-Path $env:BOB_AI_ROOT 'ops'
    } else {
        $common = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
        if (Test-Path -LiteralPath $common) {
            try {
                . $common
                $ai = Get-BobiverseAiRoot
                if ($ai) {
                    $cand = Join-Path $ai 'ops'
                    if (Test-Path -LiteralPath $cand) { $OpsRoot = $cand }
                }
            } catch { }
        }
    }
}
if ($OpsRoot) {
    $py = Join-Path $OpsRoot 'auto-focus.py'
    if (Test-Path -LiteralPath $py) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $bak = Join-Path $OpsRoot ("auto-focus.py.retired-fr3190-{0}" -f $stamp)
        if ($PSCmdlet.ShouldProcess($py, "Rename to $bak")) {
            Move-Item -LiteralPath $py -Destination $bak -Force
            Write-Retire "FR #3190 retired ops script -> $bak"
        }
    } else {
        Write-Retire "FR #3190 ops auto-focus.py already absent under $OpsRoot"
    }
    foreach ($extra in @('BobAutoFocus.xml', 'auto-focus.xml')) {
        $x = Join-Path $OpsRoot $extra
        if (Test-Path -LiteralPath $x) {
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $bak = Join-Path $OpsRoot ("{0}.retired-fr3190-{1}" -f $extra, $stamp)
            if ($PSCmdlet.ShouldProcess($x, "Rename to $bak")) {
                Move-Item -LiteralPath $x -Destination $bak -Force
                Write-Retire "FR #3190 retired $extra -> $bak"
            }
        }
    }
} else {
    Write-Retire 'FR #3190 OpsRoot not found; task unregister only'
}

Write-Retire 'FR #3190 done: use repo-level !focus <Owner/repo> only (no per-item BobAutoFocus)'
exit 0
