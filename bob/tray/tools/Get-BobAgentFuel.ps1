<#
.SYNOPSIS
  Print the agent-fuel readings bob-worker.exe uses to pick grok -> cursor -> opencode -> dialog (FR #3997 / #6120). JSON on stdout, nothing else.
.DESCRIPTION
  LOCAL readings only (CAST IRON, same sources as the tray): Cursor pools via Get-BobCursorAgentWeeklyRemaining
  (tools\Get-CursorAgentUsage.py or BOB_CURSOR_AGENT_FIXTURE; high-cost-models + auto/low-cost + on-demand), then
  Get-BobCursorGroupRemainFromLocalDoc (exported from BobBridge). Grok via Get-BobWeeklyRemaining (unified.jsonl)
  + Get-BobGrokAvailability. Never prints a key, token or path to a credential. Exit code is always 0.
  A failed Cursor reader sets cursor.error (stage text, paths stripped) and leaves high/low null (= unknown).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [ValidateSet('all', 'cursor', 'grok', 'opencode')]
    [string]$Provider = 'all'
)

$ErrorActionPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $PSScriptRoot }
$out = [ordered]@{ ok = $false; cursor = [ordered]@{ high = $null; low = $null; any = $null; on_demand_used_cents = $null; on_demand_limit_cents = $null; on_demand_remaining_pct = $null; overspend_state = $null }; grok = [ordered]@{ remaining_pct = $null; state = 'unknown'; reason = '' }; opencode = [ordered]@{ free = $null; go = $null; models = [ordered]@{}; free_model_ids = @() } }
try {
    $psd1 = Join-Path $InstallRoot 'src\BobBridge.psd1'
    if (-not (Test-Path -LiteralPath $psd1)) { throw 'no BobBridge' }
    Import-Module $psd1 -Force -ErrorAction Stop
    $out.ok = $true
    if ($Provider -eq 'all' -or $Provider -eq 'cursor') {
    try {
        if ($env:BOB_AGENT_FUEL_CURSOR_FAULT) { throw [string]$env:BOB_AGENT_FUEL_CURSOR_FAULT }
        $doc = Get-BobCursorAgentWeeklyRemaining
        if ($doc) {
            $hi = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $doc -GroupId 'high-cost-models'
            $lo = Get-BobCursorGroupRemainFromLocalDoc -LocalCursorDoc $doc -GroupId 'auto'
            if ($null -ne $hi) { $out.cursor.high = [int]$hi }
            if ($null -ne $lo) { $out.cursor.low = [int]$lo }
            $vals = @($hi, $lo) | Where-Object { $null -ne $_ }
            if ($vals.Count) { $out.cursor.any = [int](($vals | Measure-Object -Maximum).Maximum) }
            # FR #6119: surface on-demand spend limit so bob-worker treats at-limit as out-of-fuel
            # even when high/low remain % still looks non-zero (flamingo class).
            if ($null -ne $doc.on_demand_used_cents -and [string]$doc.on_demand_used_cents -ne '') {
                try { $out.cursor.on_demand_used_cents = [int]$doc.on_demand_used_cents } catch { }
            }
            if ($null -ne $doc.on_demand_limit_cents -and [string]$doc.on_demand_limit_cents -ne '') {
                try { $out.cursor.on_demand_limit_cents = [int]$doc.on_demand_limit_cents } catch { }
            }
            if ($null -ne $doc.on_demand_remaining_pct -and [string]$doc.on_demand_remaining_pct -ne '') {
                try { $out.cursor.on_demand_remaining_pct = [int]$doc.on_demand_remaining_pct } catch { }
            }
            if ($doc.overspend_state) {
                $out.cursor.overspend_state = [string]$doc.overspend_state
            }
        }
    } catch {
        $raw = [string]$_.Exception.Message
        if (-not $raw) { $raw = [string]$_.FullyQualifiedErrorId }
        if (-not $raw) { $raw = 'cursor-reader-failed' }
        $raw = [regex]::Replace($raw, '[A-Za-z]:\\[^\s''"]+', '<path>')
        if ($raw.Length -gt 180) { $raw = $raw.Substring(0, 180) }
        $out.cursor.error = $raw
    }
    }
    if ($Provider -eq 'all' -or $Provider -eq 'grok') {
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
    }
    if ($Provider -eq 'all' -or $Provider -eq 'opencode') {
    try {
        $opHelper = Join-Path $PSScriptRoot 'Get-BobOpencodeFuel.ps1'
        if (Test-Path -LiteralPath $opHelper) {
            $opRaw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $opHelper 2>$null
            if ($opRaw) {
                $op = $opRaw | ConvertFrom-Json -ErrorAction Stop
                if ($op.free -ne $null) { $out.opencode.free = [int]$op.free }
                if ($op.go -ne $null) { $out.opencode.go = [int]$op.go }
                if ($op.models) {
                    $op.models | Get-Member -MemberType NoteProperty | ForEach-Object {
                        $out.opencode.models[$_.Name] = [int]$op.models.($_.Name)
                    }
                }
                if ($op.free_model_ids) {
                    $out.opencode.free_model_ids = @($op.free_model_ids)
                }
            }
        }
    } catch { }
    }
} catch { $out.ok = $false }
[Console]::Out.WriteLine(($out | ConvertTo-Json -Compress -Depth 5))
exit 0