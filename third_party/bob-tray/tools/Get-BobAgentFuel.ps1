<#
.SYNOPSIS
  Print the agent-fuel readings bob-worker.exe uses to pick cursor -> grok -> dialog. JSON on stdout, nothing else.
.DESCRIPTION
  LOCAL readings only (CAST IRON, same sources as the tray): Cursor pools via Get-BobCursorAgentWeeklyRemaining
  (tools\Get-CursorAgentUsage.py; high-cost-models + auto/low-cost), Grok via Get-BobWeeklyRemaining (unified.jsonl)
  + Get-BobGrokAvailability. Never prints a key, token or path to a credential. Exit code is always 0; a failed
  reader yields null (= unknown), which the exe treats as "not available".
#>
[CmdletBinding()]
param([string]$InstallRoot = '')

$ErrorActionPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
$out = [ordered]@{ ok = $false; cursor = [ordered]@{ high = $null; low = $null; any = $null }; grok = [ordered]@{ remaining_pct = $null; state = 'unknown'; reason = '' } }
try {
    $psd1 = Join-Path $InstallRoot 'src\BobBridge.psd1'
    if (-not (Test-Path -LiteralPath $psd1)) { throw 'no BobBridge' }
    Import-Module $psd1 -Force -ErrorAction Stop
    $out.ok = $true
    try {
        $doc = Get-BobCursorAgentWeeklyRemaining
        if ($doc) {
            $hi = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $doc -GroupId 'high-cost-models'
            $lo = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $doc -GroupId 'auto'
            if ($null -ne $hi) { $out.cursor.high = [int]$hi }
            if ($null -ne $lo) { $out.cursor.low = [int]$lo }
            $vals = @($hi, $lo) | Where-Object { $null -ne $_ }
            if ($vals.Count) { $out.cursor.any = [int](($vals | Measure-Object -Maximum).Maximum) }
        }
    } catch { }
    try {
        $w = Get-BobWeeklyRemaining
        $auth = $null
        try { $auth = Get-BobGrokAuthSnapshot } catch { }
        $av = Get-BobGrokAvailability -Weekly $w -Auth $auth
        if ($av) {
            $out.grok.state = [string]$av.state
            $out.grok.reason = [string]$av.reason
            if ($null -ne $av.remaining_pct) { $out.grok.remaining_pct = [int]$av.remaining_pct }
        }
        if ($null -eq $out.grok.remaining_pct -and $w -and $null -ne $w.remaining_pct -and [string]$w.remaining_pct -ne '') {
            $out.grok.remaining_pct = [int]$w.remaining_pct
        }
    } catch { }
} catch { $out.ok = $false }
[Console]::Out.WriteLine(($out | ConvertTo-Json -Compress -Depth 5))
exit 0