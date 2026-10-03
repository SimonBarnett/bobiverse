<#
.SYNOPSIS
  Report / reclaim non-worktree seat disk headroom when C: is low (FR #890).

.DESCRIPTION
  After job-worktree prune (FR #877), boxes can still sit near 0 free GB because
  ~/.grok/sessions, ~/.grok/downloads, pip/npm caches, and old C:\ai\backup-*
  trees dominate. This helper:

  - Always prints FreeGB and a short size report for known consumers.
  - With -Reclaim (and FreeGB < MinFreeGB, or -Force): removes safe caches:
    grok downloads, pr-merge-clones, aged grok sessions (keeps -KeepSessionId
    and sessions newer than -KeepSessionHours), pip/npm caches, aged files in
    Windows\Temp, optional aged C:\ai\backup-* (-IncludeAiBackups).

  Never touches Ergo, ircd.yaml, secrets, the current seat session id, or
  running services. Pair with Clear-BobiverseJobWorktrees.ps1 for linked trees.

.EXAMPLE
  ..\scripts\Clear-BobiverseSeatDisk.ps1 -Reclaim -KeepSessionId 0ee19a2a-...
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [double]$MinFreeGB = 2,
    [string]$KeepSessionId = '',
    [int]$KeepSessionHours = 6,
    [string]$GrokHome = '',
    [string]$AiRoot = 'C:\ai',
    [switch]$IncludeAiBackups,
    [switch]$Reclaim,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FreeGB {
    $d = Get-PSDrive -Name C -ErrorAction Stop
    return [math]::Round(([double]$d.Free) / 1GB, 2)
}

function Get-FolderGB([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $fso = New-Object -ComObject Scripting.FileSystemObject
        $sz = [int64]$fso.GetFolder($Path).Size
        return [math]::Round($sz / 1GB, 2)
    } catch {
        return $null
    }
}

function Remove-TreeSafe([string]$Path, [string]$Why) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    if ($WhatIfPreference) {
        Write-Host "WhatIf: remove $Path ($Why)"
        return 1
    }
    if ($PSCmdlet.ShouldProcess($Path, "remove ($Why)")) {
        Write-Host "Removing $Path ($Why)"
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        return 1
    }
    return 0
}

if (-not $GrokHome) {
    $GrokHome = Join-Path $env:USERPROFILE '.grok'
}

$free = Get-FreeGB
Write-Host ("FreeGB={0} MinFreeGB={1} Reclaim={2} Force={3}" -f $free, $MinFreeGB, [bool]$Reclaim, [bool]$Force)

$report = @(
    (Join-Path $GrokHome 'sessions'),
    (Join-Path $GrokHome 'downloads'),
    (Join-Path $GrokHome 'pr-merge-clones'),
    (Join-Path $GrokHome 'bin'),
    (Join-Path $env:LOCALAPPDATA 'pip\Cache'),
    (Join-Path $env:LOCALAPPDATA 'npm-cache'),
    (Join-Path $env:USERPROFILE '.cursor\chats'),
    'C:\Windows\Temp'
)
if ($AiRoot) {
    $report += $AiRoot
}

Write-Host '--- size report (GB) ---'
foreach ($p in $report) {
    $gb = Get-FolderGB $p
    if ($null -eq $gb) {
        Write-Host ("  (missing) {0}" -f $p)
    } else {
        Write-Host ("  {0,7:N2}  {1}" -f $gb, $p)
    }
}

$need = $Force -or ($free -lt $MinFreeGB)
if (-not $Reclaim) {
    Write-Host 'Report only (pass -Reclaim to delete safe caches when FreeGB < MinFreeGB, or -Force).'
    return
}
if (-not $need) {
    Write-Host 'OK: free space above MinFreeGB; pass -Force to reclaim anyway.'
    return
}

$removed = 0
$downloads = Join-Path $GrokHome 'downloads'
if (Test-Path -LiteralPath $downloads) {
    Get-ChildItem -LiteralPath $downloads -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $removed += Remove-TreeSafe $_.FullName 'grok downloads'
    }
}

$clones = Join-Path $GrokHome 'pr-merge-clones'
if (Test-Path -LiteralPath $clones) {
    Get-ChildItem -LiteralPath $clones -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $removed += Remove-TreeSafe $_.FullName 'grok pr-merge-clones'
    }
}

$pip = Join-Path $env:LOCALAPPDATA 'pip\Cache'
if (Test-Path -LiteralPath $pip) {
    Get-ChildItem -LiteralPath $pip -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $removed += Remove-TreeSafe $_.FullName 'pip cache'
    }
}
$npm = Join-Path $env:LOCALAPPDATA 'npm-cache'
if (Test-Path -LiteralPath $npm) {
    Get-ChildItem -LiteralPath $npm -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $removed += Remove-TreeSafe $_.FullName 'npm-cache'
    }
}

$cut = (Get-Date).AddHours(-1 * [Math]::Abs($KeepSessionHours))
$sessRoot = Join-Path $GrokHome 'sessions'
if (Test-Path -LiteralPath $sessRoot) {
    Get-ChildItem -LiteralPath $sessRoot -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if ($KeepSessionId -and ($_.Name -like ("*{0}*" -f $KeepSessionId))) { return }
        if ($_.LastWriteTime -gt $cut) { return }
        $removed += Remove-TreeSafe $_.FullName 'aged grok session'
    }
}

Get-ChildItem -LiteralPath 'C:\Windows\Temp' -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-3) } |
    ForEach-Object {
        $removed += Remove-TreeSafe $_.FullName 'aged Windows\\Temp file'
    }

if ($IncludeAiBackups -and $AiRoot -and (Test-Path -LiteralPath $AiRoot)) {
    Get-ChildItem -LiteralPath $AiRoot -Directory -Filter 'backup-*' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-2) } |
        ForEach-Object {
            $removed += Remove-TreeSafe $_.FullName 'aged C:\\ai\\backup-*'
        }
}

$freeNow = Get-FreeGB
Write-Host ("Done removed_ops={0} FreeGB_now={1}" -f $removed, $freeNow)
