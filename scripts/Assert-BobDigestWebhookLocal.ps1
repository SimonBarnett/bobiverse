#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke: Write-BobIrcStatus with BOB_DIGEST_WEBHOOK_CAPTURE; assert machine id / weekly / overage.
.PARAMETER InstallRoot
  Staged or live bob tree containing src\BobBridge.psd1 (default C:\ai\bob, else third_party\bob-tray).
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = '',
    [string]$CapturePath = '',
    [string]$MachineId = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-BobTrayModuleRoot {
    param([string]$Preferred)
    foreach ($c in @(
            $Preferred,
            (Join-Path 'C:\ai\bob' ''),
            (Join-Path $repoRoot 'third_party\bob-tray'),
            (Join-Path $repoRoot 'dist\bob-*')
        )) {
        if (-not $c) { continue }
        if ($c -match '\*') {
            $hit = Get-ChildItem -Path (Split-Path $c -Parent) -Directory -Filter (Split-Path $c -Leaf) -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($hit) { $c = $hit.FullName }
            else { continue }
        }
        $psd1 = Join-Path $c 'src\BobBridge.psd1'
        if (Test-Path -LiteralPath $psd1) { return [IO.Path]::GetFullPath($c) }
    }
    return $null
}

$root = Resolve-BobTrayModuleRoot -Preferred $InstallRoot
if (-not $root) {
    throw 'BobBridge not found (pass -InstallRoot to staged bob tree or run Sync-BobTrayFromAgenticBuild)'
}
$psd1 = Join-Path $root 'src\BobBridge.psd1'
Write-Host "INFO Import-Module $psd1"
Import-Module $psd1 -Force

if (-not $MachineId) {
    $MachineId = ([string]$env:BOB_MACHINE_ID).Trim()
}
if (-not $MachineId) {
    try { $MachineId = [string](Get-ThisMachineId) } catch { $MachineId = '' }
}
if (-not $MachineId) {
    $MachineId = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]+', '-').Trim('-_').ToLowerInvariant()
}
$env:BOB_MACHINE_ID = $MachineId
if (-not $env:BOB_BRIDGE_HOME) {
    $env:BOB_BRIDGE_HOME = Join-Path $env:USERPROFILE '.grok\bob-bridge'
}
if (-not $env:BOB_IRC_HOME) {
    $env:BOB_IRC_HOME = Join-Path $env:USERPROFILE '.agentic-irc-bobiverse'
}
New-Item -ItemType Directory -Force -Path $env:BOB_BRIDGE_HOME, $env:BOB_IRC_HOME | Out-Null

if (-not $CapturePath) {
    $CapturePath = Join-Path $env:TEMP ("bob-digest-capture-{0}.ndjson" -f [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
}
if (Test-Path -LiteralPath $CapturePath) { Remove-Item -LiteralPath $CapturePath -Force }
$env:BOB_DIGEST_WEBHOOK_CAPTURE = $CapturePath

$weekBefore = $null
try { $weekBefore = Get-BobWeeklyRemaining } catch { $weekBefore = $null }
$overBefore = $null
try {
    if (Get-Command Get-BobCursorOverageGbp -ErrorAction SilentlyContinue) {
        $overBefore = Get-BobCursorOverageGbp
    }
} catch { $overBefore = $null }

Write-Host ("INFO Write-BobIrcStatus machine={0} capture={1}" -f $MachineId, $CapturePath)
$null = Write-BobIrcStatus

if (-not (Test-Path -LiteralPath $CapturePath)) {
    throw "capture file missing after Write-BobIrcStatus: $CapturePath (report.secret / reportUrl may be required when capture unset; capture env should short-circuit HTTP)"
}

$raw = Get-Content -LiteralPath $CapturePath -Raw -ErrorAction Stop
$line = ($raw -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 1)
if (-not $line) { throw "capture empty: $CapturePath" }
$doc = $line | ConvertFrom-Json

$fail = @()
$gotId = [string]$doc.machine
if (-not $gotId) { $gotId = [string]$doc.id }
if (-not $gotId) { $gotId = [string]$doc.Machine }
if ($gotId -ne $MachineId) {
    # merge payload uses machine=; allow id match
    if ([string]$doc.id -ne $MachineId -and [string]$doc.machine -ne $MachineId) {
        $fail += "machine id expected=$MachineId got id=$($doc.id) machine=$($doc.machine)"
    }
}

if ($null -ne $weekBefore -and $null -ne $weekBefore.remaining_pct) {
    $wantWeek = [int]$weekBefore.remaining_pct
    $gotWeek = $null
    if ($null -ne $doc.weekly -and [string]$doc.weekly -ne '') {
        try { $gotWeek = [int]$doc.weekly } catch { $gotWeek = $null }
    }
    if ($gotWeek -ne $wantWeek) {
        $fail += "weekly expected=$wantWeek got=$gotWeek"
    }
} else {
    Write-Host 'INFO Get-BobWeeklyRemaining unavailable - skip weekly assert'
}

$localOver = $null
if ($null -ne $overBefore -and [string]$overBefore -ne '') {
    try { $localOver = [double]$overBefore } catch { $localOver = $null }
}
if ($null -eq $localOver) {
    try {
        if ($doc.PSObject.Properties.Name -contains 'overage_gbp' -and $null -ne $doc.overage_gbp) {
            # nothing
        }
    } catch { }
}
if ($null -ne $localOver -and $localOver -gt 0) {
    if ($null -eq $doc.overage_gbp -or [string]$doc.overage_gbp -eq '') {
        $fail += "overage_gbp missing while local overage=$localOver"
    } else {
        Write-Host ("INFO overage_gbp={0} (local={1})" -f $doc.overage_gbp, $localOver)
    }
} else {
    Write-Host 'INFO local overage not > 0 - skip overage_gbp presence assert'
}

if ($fail.Count -gt 0) {
    Write-Host 'FAIL Assert-BobDigestWebhookLocal:'
    $fail | ForEach-Object { Write-Host "  - $_" }
    Write-Host ("capture line: {0}" -f $line.Substring(0, [Math]::Min(400, $line.Length)))
    exit 1
}

Write-Host ("PASS Assert-BobDigestWebhookLocal machine={0} capture={1}" -f $MachineId, $CapturePath)
exit 0
