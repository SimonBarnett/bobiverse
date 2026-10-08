<#
.SYNOPSIS
  Remove leftover FR/MRB/UAT git worktrees when C: is low on free space (FR #877).

.DESCRIPTION
  Linked job trees under %TEMP%\bobiverse-* (and similar) accumulate until
  `git worktree add` fails with "No space left on device". After DONE (or before
  a new job tree), seats run this helper:

  - If FreeGB on the repo drive is below MinFreeGB (default 2), remove other job
    worktrees (keep the install root and optional -KeepPath) and orphan TEMP dirs.
  - FR #1661 earlier prune / soft cap: even when FreeGB >= MinFreeGB, remove job
    worktrees beyond -MaxExtraJobTrees (default 0 = keep only -KeepPath + install
    root) so seats do not wait until FreeGB is critical.
  - Always `git worktree prune` when removals happened (or with -Force).
  - Orphan %TEMP%\bobiverse-* directories not registered as worktrees are removed
    on low disk / -Force (full reclaim).
  - FR #2727: never selects operator/build trees (`wt-bob-main-*`, `wt-airc-*`,
    `wt-main`). Skips trees with a live `.bobiverse-seat` marker or a
    git/python/PyInstaller process whose CommandLine cites the path. This script
    is the only sanctioned reclaim path - seats must not hand-delete other
    `C:\ai\*` trees when removed=0.

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

function Test-IsOperatorOrNonJobLeaf([string]$Leaf) {
    # FR #2727: operator hotpatch / airc build trees must never be reclaim candidates.
    if (-not $Leaf) { return $true }
    if ($Leaf -match '(?i)^wt-bob-main($|-)') { return $true }
    if ($Leaf -match '(?i)^wt-airc($|-)') { return $true }
    if ($Leaf -match '(?i)^wt-main$') { return $true }
    return $false
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
    if (Test-IsOperatorOrNonJobLeaf $leaf) { return $false }
    $temp = [System.IO.Path]::GetFullPath($env:TEMP)
    if ($full.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -and ($leaf -match '(?i)^bobiverse-')) {
        return $true
    }
    # Durable job trees under C:\ai (or D:\...): bob-wt-fr-N / job-fr-N / docs-mrb-N ...
    if ($leaf -match '(?i)^(bob-wt-|job-)?(fr|mrb|uat|docs-mrb)-\d') { return $true }
    if ($leaf -match '(?i)^(bobiverse-|fr-\d|mrb-|uat-)') { return $true }
    # Temp-style ...-wt suffix only when the leaf already looks like a job id.
    if ($leaf -match '(?i)^(bobiverse-|fr-|mrb-|uat-|docs-mrb-).*-wt$') { return $true }
    return $false
}

function Test-WorktreeProtected([string]$Path) {
    # True when a live seat marker or busy tool process owns the tree (FR #2727).
    if (-not $Path) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    } catch {
        return $false
    }
    $marker = Join-Path $full '.bobiverse-seat'
    if (Test-Path -LiteralPath $marker) {
        try {
            $raw = Get-Content -LiteralPath $marker -Raw -Encoding UTF8
            $obj = $raw | ConvertFrom-Json
            $seatPid = 0
            if ($obj.PSObject.Properties.Name -contains 'pid') {
                $seatPid = [int]$obj.pid
            }
            if ($seatPid -gt 0) {
                $alive = Get-Process -Id $seatPid -ErrorAction SilentlyContinue
                if ($null -ne $alive) {
                    return $true
                }
            }
        } catch {
            # Malformed marker: do not treat as protected forever.
        }
    }
    # Busy tool heuristic: CommandLine cites this path (cwd is not exposed via CIM).
    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^(git|python|pyinstaller|py|pwsh|powershell)\.exe$' })
    foreach ($proc in $procs) {
        $cl = [string]$proc.CommandLine
        if ($cl -and $cl.IndexOf($full, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
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

# FR #1661: low-disk / -Force = full reclaim; soft cap still runs when FreeGB is healthy.
$lowDisk = $Force -or ($freeGb -lt $MinFreeGB)

# FR #1740 / #1664: force Object[] of line strings - a single-line git capture is a scalar string and
# `foreach` would iterate characters under StrictMode.
$list = @(
    & git -C $rootFull worktree list --porcelain 2>&1 |
        ForEach-Object { "$_" } |
        Where-Object { $_ -ne '' }
)
if ($LASTEXITCODE -ne 0) {
    throw "git worktree list failed: $($list -join "`n")"
}

$paths = New-Object System.Collections.Generic.List[string]
foreach ($line in $list) {
    if ($line -match '^worktree (.+)$') {
        [void]$paths.Add($Matches[1])
    }
}

$removed = 0
$skippedProtected = 0
# FR #1664 / #1740: pipeline/filter of one path is a scalar string; always force Object[] before .Count (StrictMode).
$jobTrees = @($paths.ToArray() | Where-Object { Test-IsJobWorktreePath $_ $rootFull $keepFull })
$jobTrees = @($jobTrees)
# FR #2727: drop live-seat / busy-tool trees before cap math (even with -Force).
$protectedTrees = @($jobTrees | Where-Object { Test-WorktreeProtected $_ })
$jobTrees = @($jobTrees | Where-Object { -not (Test-WorktreeProtected $_) })
foreach ($pt in $protectedTrees) {
    Write-Host "FR #2727 skip protected worktree $pt"
    $skippedProtected++
}

# Cap: remove extras beyond MaxExtraJobTrees (oldest first by path mtime when possible).
# FR #1661 soft cap: enforce this even when FreeGB >= MinFreeGB (earlier prune gate).
$jobTreeCount = @($jobTrees).Count
$softCapNeeded = ($MaxExtraJobTrees -ge 0 -and $jobTreeCount -gt $MaxExtraJobTrees)
if (-not $lowDisk -and -not $softCapNeeded) {
    Write-Host "OK: free space above MinFreeGB and job-tree count within MaxExtraJobTrees; pass -Force to prune anyway."
    if ($skippedProtected -gt 0) {
        Write-Host ("FR #2727 skipped_protected={0}" -f $skippedProtected)
    }
    return
}

if ($lowDisk) {
    # Full reclaim: remove every job tree (KeepPath / install root already excluded).
    $toRemove = @($jobTrees)
    Write-Host ("FR #1661 full reclaim: lowDisk/Force removing {0} job worktree(s)" -f @($toRemove).Count)
} elseif ($softCapNeeded) {
    # FR #1664: Sort-Object of a single path returns a scalar; wrap with @() before .Count.
    $sorted = @($jobTrees | Sort-Object {
        if (Test-Path -LiteralPath $_) {
            (Get-Item -LiteralPath $_).LastWriteTimeUtc
        } else {
            [datetime]::MinValue
        }
    })
    $sortedCount = @($sorted).Count
    $toRemove = @($sorted | Select-Object -First ([Math]::Max(0, $sortedCount - $MaxExtraJobTrees)))
    Write-Host ("FR #1661 earlier prune / soft cap: removing {0} extra job worktree(s) (MaxExtraJobTrees={1})" -f @($toRemove).Count, $MaxExtraJobTrees)
} else {
    $toRemove = @()
}

foreach ($p in $toRemove) {
    if ($WhatIfPreference) {
        Write-Host "WhatIf: git worktree remove --force $p"
        $removed++
        continue
    }
    if ($PSCmdlet.ShouldProcess($p, 'git worktree remove --force')) {
        Write-Host "Removing worktree $p"
        # FR #2460: under StrictMode + ErrorActionPreference Stop, git stderr piped as
        # ErrorRecords (e.g. Permission denied) can terminate before LASTEXITCODE fallback.
        # Stringify every record so native stderr stays non-terminating.
        $gitOut = @(
            & git -C $rootFull worktree remove --force $p 2>&1 |
                ForEach-Object { "$_" }
        )
        $gitExit = $LASTEXITCODE
        foreach ($line in $gitOut) {
            if ($line) { Write-Host $line }
        }
        if ($gitExit -ne 0) {
            Write-Warning "worktree remove failed for $p (will try prune / rmdir)"
            if (Test-Path -LiteralPath $p) {
                Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        $removed++
    }
}

# Orphan TEMP bobiverse-* dirs (full reclaim only - FR #1661 soft cap leaves orphans alone)
$tempRoot = $env:TEMP
if ($lowDisk -and $tempRoot -and (Test-Path -LiteralPath $tempRoot)) {
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
        # FR #2460: same stderr ErrorRecord hardening as worktree remove.
        $pruneOut = @(
            & git -C $rootFull worktree prune 2>&1 |
                ForEach-Object { "$_" }
        )
        foreach ($line in $pruneOut) {
            if ($line) { Write-Host $line }
        }
    }
}

$freeAfter = Get-FreeGB $rootFull
Write-Host ("Done removed={0} FreeGB_now={1} skipped_protected={2}" -f $removed, $freeAfter, $skippedProtected)
