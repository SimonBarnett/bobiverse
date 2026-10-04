<#
.SYNOPSIS
  Remove leftover FR/MRB/UAT git worktrees when C: is low on free space (FR #877).

.DESCRIPTION
  Linked job trees under %TEMP%\bobiverse-* (and similar) accumulate until
  `git worktree add` fails with "No space left on device". After DONE (or before
  a new job tree), seats run this helper:

  - If FreeGB on the repo drive is below MinFreeGB (default 2), remove other job
    worktrees (keep the install root and optional -KeepPath).
  - Always `git worktree prune` when removals happened (or with -Force).
  - Orphan %TEMP%\bobiverse-* directories not registered as worktrees are removed too.

  Never touches Ergo, never kills seats, never deletes the -RepoRoot install tree.

.EXAMPLE
  ..\scripts\Clear-BobiverseJobWorktrees.ps1 -RepoRoot C:\ai\bob -KeepPath $env:TEMP\bobiverse-fr877-wt
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [double]$MinFreeGB = 2,
    [int]$MaxExtraJobTrees = 0,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FreeGB([string]$Path) {
    $root = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $Path).Path)
    $driveLetter = $root.TrimEnd('\').TrimEnd(':')
    $d = Get-PSDrive -Name $driveLetter -ErrorAction Stop
    return [math]::Round(([double]$d.Free) / 1GB, 2)
}

function Test-IsJobWorktreePath([string]$Path, [string]$RootFull, [string]$KeepFull) {
    if (-not $Path) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return $false
    }
    if ($full.TrimEnd('\') -ieq $RootFull.TrimEnd('\')) { return $false }
    if ($KeepFull -and ($full.TrimEnd('\') -ieq $KeepFull.TrimEnd('\'))) { return $false }
    $leaf = Split-Path -Leaf $full
    $temp = [System.IO.Path]::GetFullPath($env:TEMP)
    if ($full.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -and ($leaf -match '(?i)^bobiverse-')) {
        return $true
    }
    if ($leaf -match '(?i)^(bobiverse-|fr-\d|mrb-|uat-)') { return $true }
    if ($leaf -match '(?i)-wt$') { return $true }
    return $false
}

if (-not $RepoRoot) {
    # common/scripts -> repo root
    $here = $PSScriptRoot
    if ($here -and (Test-Path -LiteralPath (Join-Path $here '..\..\bob'))) {
        $RepoRoot = (Resolve-Path -LiteralPath (Join-Path $here '..\..')).Path
    } elseif (Test-Path -LiteralPath 'C:\ai\bob\.git') {
        $RepoRoot = 'C:\ai\bob'
    } else {
        throw 'RepoRoot required (path to the bobiverse install / clone with .git).'
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git'))) {
    throw "RepoRoot '$RepoRoot' has no .git"
}

$rootFull = [System.IO.Path]::GetFullPath($RepoRoot)
$keepFull = ''
if ($KeepPath) {
    $keepFull = [System.IO.Path]::GetFullPath($KeepPath)
}

$freeGb = Get-FreeGB $rootFull
Write-Host ("FreeGB={0} MinFreeGB={1} RepoRoot={2} KeepPath={3}" -f $freeGb, $MinFreeGB, $rootFull, $keepFull)

$need = $Force -or ($freeGb -lt $MinFreeGB)
if (-not $need) {
    Write-Host "OK: free space above MinFreeGB; pass -Force to prune job trees anyway."
    return
}

$list = & git -C $rootFull worktree list --porcelain 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "git worktree list failed: $list"
}

$paths = @()
foreach ($line in $list) {
    if ($line -match '^worktree (.+)$') {
        $paths += $Matches[1]
    }
}

$removed = 0
# FR #1664: pipeline/filter of one path is a scalar string; always force Object[] before .Count (StrictMode).
$jobTrees = @($paths | Where-Object { Test-IsJobWorktreePath $_ $rootFull $keepFull })

# Cap: remove extras beyond MaxExtraJobTrees (oldest first by path mtime when possible)
if ($MaxExtraJobTrees -ge 0 -and $jobTrees.Count -gt $MaxExtraJobTrees) {
    # FR #1664: Sort-Object of a single path returns a scalar; wrap with @() before .Count.
    $sorted = @($jobTrees | Sort-Object {
        if (Test-Path -LiteralPath $_) {
            (Get-Item -LiteralPath $_).LastWriteTimeUtc
        } else {
            [datetime]::MinValue
        }
    })
    $toRemove = @($sorted | Select-Object -First ([Math]::Max(0, $sorted.Count - $MaxExtraJobTrees)))
} else {
    $toRemove = @($jobTrees)
}

foreach ($p in $toRemove) {
    if ($WhatIfPreference) {
        Write-Host "WhatIf: git worktree remove --force $p"
        $removed++
        continue
    }
    if ($PSCmdlet.ShouldProcess($p, 'git worktree remove --force')) {
        Write-Host "Removing worktree $p"
        & git -C $rootFull worktree remove --force $p 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "worktree remove failed for $p (will try prune / rmdir)"
            if (Test-Path -LiteralPath $p) {
                Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        $removed++
    }
}

# Orphan TEMP bobiverse-* dirs
$tempRoot = $env:TEMP
if ($tempRoot -and (Test-Path -LiteralPath $tempRoot)) {
    Get-ChildItem -LiteralPath $tempRoot -Directory -Filter 'bobiverse-*' -ErrorAction SilentlyContinue | ForEach-Object {
        $full = $_.FullName
        if ($keepFull -and ($full.TrimEnd('\') -ieq $keepFull.TrimEnd('\'))) { return }
        $stillListed = $false
        foreach ($p in $paths) {
            try {
                if ([System.IO.Path]::GetFullPath($p).TrimEnd('\') -ieq $full.TrimEnd('\')) { $stillListed = $true; break }
            } catch { }
        }
        if ($stillListed) { return }
        if ($WhatIfPreference) {
            Write-Host "WhatIf: Remove-Item orphan $full"
            $removed++
            return
        }
        if ($PSCmdlet.ShouldProcess($full, 'Remove orphan bobiverse-* directory')) {
            Write-Host "Removing orphan $full"
            Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
            $removed++
        }
    }
}

if ($removed -gt 0 -or $Force) {
    if ($WhatIfPreference) {
        Write-Host "WhatIf: git worktree prune"
    } else {
        Write-Host "Pruning worktree metadata"
        & git -C $rootFull worktree prune 2>&1 | Out-Host
    }
}

$freeAfter = Get-FreeGB $rootFull
Write-Host ("Done removed={0} FreeGB_now={1}" -f $removed, $freeAfter)
