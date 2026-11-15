#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7510 / #7580 / #7604: poll the bob digest and write run\tray-digest-pools.json for TipForm/Status.
.DESCRIPTION
  Invoked by bob-tray.exe on a 60s timer (engine alive or not). Pool % for Status/TipForm
  comes only from this file, painted as the digest publishes (no local age stale). UTF-8 no BOM.
  Fetch failure keeps last rows and writes tray-digest-fetch-fail.json for CrashHook. Never prints secrets.
  FR #7604: works standalone (Get-BobTrayDigestReportUrl lives in Get-BobTrayHover.ps1); every run
  writes pools and/or the fail file with reason + timestamp; empty URL / exceptions report to bobiverse.
.PARAMETER Root
  Install root (contains run\).
.PARAMETER Url
  Optional digest URL (default Get-BobTrayDigestReportUrl / canonical).
.PARAMETER DigestPath
  Optional fixture JSON path (tests); skips HTTP.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [string]$Url = '',
    [string]$DigestPath = ''
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)

function Write-BobTrayDigestPoolsScriptFail {
    param([string]$RootPath, [string]$Reason, [string]$ErrorText = '')
    $run = Join-Path $RootPath 'run'
    try {
        if (-not (Test-Path -LiteralPath $run)) { New-Item -ItemType Directory -Force -Path $run | Out-Null }
    } catch { }
    $reason = ([string]$Reason).Trim()
    if (-not $reason) { $reason = 'Update-BobTrayDigestPools.ps1 failed' }
    $err = ([string]$ErrorText).Trim()
    $err = ($err -replace '(?i)(bearer\s+)\S+', '$1***' -replace '(?i)(token[=:]\s*)\S+', '$1***' -replace '(?i)(password[=:]\s*)\S+', '$1***')
    if ($err.Length -gt 240) { $err = $err.Substring(0, 240) }
    if ($reason.Length -gt 240) { $reason = $reason.Substring(0, 240) }
    $failFlag = Join-Path $run 'tray-digest-fetch-fail.json'
    $failDoc = [ordered]@{
        v      = 1
        ts     = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        reason = $reason
        note   = $reason
        error  = $(if ($err) { $err } else { $reason })
    }
    try {
        $failTmp = $failFlag + '.tmp'
        [IO.File]::WriteAllText($failTmp, (ConvertTo-Json -InputObject $failDoc -Compress), (New-Object System.Text.UTF8Encoding $false))
        if (Test-Path -LiteralPath $failFlag) {
            [IO.File]::Replace($failTmp, $failFlag, [NullString]::Value)
        } else {
            [IO.File]::Move($failTmp, $failFlag)
        }
    } catch { }
    try {
        if (Get-Command Report-BobDeterministicException -ErrorAction SilentlyContinue) {
            $ex = New-Object System.InvalidOperationException ($reason + $(if ($err) { ': ' + $err } else { '' }))
            Report-BobDeterministicException -Site 'Update-BobTrayDigestPools.ps1' -Exception $ex -ScriptPath $PSCommandPath -Repo 'SimonBarnett/bobiverse' | Out-Null
        }
    } catch { }
}

try {
    # Resolve BobBridge / Hover helpers (flat install or repo tray tree).
    $candidates = @(
        (Join-Path $Root 'src\Public\Get-BobTrayHover.ps1'),
        (Join-Path $Root 'tray\src\Public\Get-BobTrayHover.ps1'),
        (Join-Path (Split-Path $PSScriptRoot -Parent) 'src\Public\Get-BobTrayHover.ps1')
    )
    $hover = $null
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c -PathType Leaf) { $hover = $c; break }
    }
    if (-not $hover) { throw 'Get-BobTrayHover.ps1 not found relative to Root/tools' }

    $dialogCandidates = @(
        (Join-Path $Root 'tools\BobTrayDialogs.ps1'),
        (Join-Path $PSScriptRoot 'BobTrayDialogs.ps1')
    )
    $reportCandidates = @(
        (Join-Path $Root 'src\Private\Report-BobDeterministicException.ps1'),
        (Join-Path $Root 'tray\src\Private\Report-BobDeterministicException.ps1'),
        (Join-Path (Split-Path $PSScriptRoot -Parent) 'src\Private\Report-BobDeterministicException.ps1')
    )
    . $hover
    foreach ($d in $dialogCandidates) {
        if (Test-Path -LiteralPath $d -PathType Leaf) { . $d; break }
    }
    foreach ($r in $reportCandidates) {
        if (Test-Path -LiteralPath $r -PathType Leaf) { . $r; break }
    }

    if (-not (Get-Command Update-BobTrayDigestPools -ErrorAction SilentlyContinue)) {
        throw 'Update-BobTrayDigestPools not loaded'
    }
    if (-not (Get-Command Get-BobTrayDigestReportUrl -ErrorAction SilentlyContinue)) {
        throw 'Get-BobTrayDigestReportUrl not loaded (FR #7604 standalone require)'
    }

    $path = Update-BobTrayDigestPools -Root $Root -Url $Url -DigestPath $DigestPath
    $run = Join-Path $Root 'run'
    $pools = Join-Path $run 'tray-digest-pools.json'
    $fail = Join-Path $run 'tray-digest-fetch-fail.json'
    # FR #7604: every standalone run must leave pools and/or fail file.
    if (-not (Test-Path -LiteralPath $pools) -and -not (Test-Path -LiteralPath $fail)) {
        Write-BobTrayDigestPoolsScriptFail -RootPath $Root -Reason 'digest updater wrote neither pools nor fail file'
    }
    if ($path) { Write-Output $path }
}
catch {
    $msg = [string]$_.Exception.Message
    Write-BobTrayDigestPoolsScriptFail -RootPath $Root -Reason ('Update-BobTrayDigestPools.ps1 exception: {0}' -f $msg) -ErrorText $msg
    # Non-zero so bob-tray / tests can see failure, but fail file is the contract.
    exit 1
}
