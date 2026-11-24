<#
.SYNOPSIS
  Remove leftover FR/MRB/UAT git worktrees when C: is low on free space (FR #877 / FR #3641 / FR #8023).

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
    on low disk / -Force only when empty or only .bobiverse-seat / cdk.out* (FR #8023).
  - FR #2727: never selects operator/build trees (`wt-bob-main-*`, `wt-airc-*`,
    `wt-main`). Skips trees with a live `.bobiverse-seat` marker or a
    git/python/PyInstaller process whose CommandLine cites the path. This script
    is the only sanctioned reclaim path - seats must not hand-delete other
    `C:\ai\*` trees when removed=0.
  - FR #3641: a fresh `.bobiverse-seat` protects mid-FR trees even when the
    recorded pid is dead/wrong (soft-cap and non-Force reclaim). -Force /
    low-disk may reclaim only when the marker mtime is older than
    -StaleSeatHours (default 48) and the pid is not an owner of this tree.
  - FR #3698: a live marker pid protects only when that process CommandLine
    cites this worktree. When RepoRoot FreeGB stays below MinFreeGB after reclaim,
    print WARN FR #3698.
  - FR #4945: product sibling leaves such as `a-search-wt-fr-N` are job trees when
    listed by that product's `git worktree list`. Pass `-RepoRoot` of the product.
  - FR #3717: before `git worktree remove`, delete `cdk.out*` under the job tree
    with `cmd rmdir /s /q`.
  - FR #9500: Access denied on cmd rmdir (e.g. locked PYTEST~1 / .pytest_cache)
    warns and continues; does not abort the Clear run (attrib -R retry once).
  - FR #4197: when a registered tree is missing or its `.git` is gone, warn, keep
    unverifiable dirs, prune metadata, and continue.
  - FR #4988: job trees also live under Get-BobiverseJobWorktreeBase.
  - FR #8023: fail-closed local-work predicate (safe|has-work|unknown). Only
    `safe` trees are removable. Publication requires a successful
    `git fetch --prune origin` then HEAD reachable from refs/remotes/origin/*
    or equal to a merged PR headRefOid. `-PruneClosedJobs` selects closed/merged
    jobs only. Named mutex on git-common-dir; busy => skipped:busy exit 0.
    `git worktree remove` without --force; no Remove-Item fallback for registered
    trees that fail remove.

  Never touches Ergo, never kills seats, never deletes the -RepoRoot install tree.

.EXAMPLE
  ..\scripts\Clear-BobiverseJobWorktrees.ps1 -RepoRoot C:\ai\bob -KeepPath $env:TEMP\bobiverse-fr877-wt

.EXAMPLE
  ..\scripts\Clear-BobiverseJobWorktrees.ps1 -PruneClosedJobs -DiscoverRepoRoots -MaxExtraJobTrees -1 -SkipSeatDisk
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [double]$MinFreeGB = 2,
    [int]$MaxExtraJobTrees = 0,
    [double]$StaleSeatHours = 48,
    [switch]$Force,
    [switch]$SkipSeatDisk,
    [string]$SeatDiskScript = '',
    [switch]$PruneClosedJobs,
    [switch]$DiscoverRepoRoots,
    [int]$MaxJobStateLookups = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'


# FR #5022: $PSScriptRoot is empty when jeeves tests Invoke-Expression the
# script body; guard Join-Path. Never treat build/recipe *-ref-* trees as job
# leaves (e.g. a-search-ref-4003).
# FR #1664 / FR #1740: pipeline/filter of one path is a scalar string; always force
# @() before .Count (StrictMode).

# FR #2460: stringify ErrorRecord from git worktree remove before $LASTEXITCODE.
# FR #3698: skip this process ($PID) - Clear / test harness CommandLines embed paths.
# FR #3717 leftover rmdir: cdk.out* pre-rmdir; Filename too long / MAX_PATH deep trees.
# FR #2460 + FR #4197: try/catch around worktree remove; continue reclaiming the rest.
# One broken registration must not abort the rest of the Clear run.
if ($PSScriptRoot) {
    $script:BobiverseCommonPs1 = Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'
    if (Test-Path -LiteralPath $script:BobiverseCommonPs1) {
        . $script:BobiverseCommonPs1
    }
}

function Get-FreeGB([string]$Path) {
    $root = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $Path).Path)
    $driveLetter = $root.TrimEnd('\').TrimEnd(':')
    $d = Get-PSDrive -Name $driveLetter -ErrorAction Stop
    return [math]::Round(([double]$d.Free) / 1GB, 2)
}

function Test-IsOperatorOrNonJobLeaf([string]$Leaf) {
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
    if ($leaf -match '(?i)^(bob-wt-|job-)?(fr|mrb|uat|docs-mrb)(-[a-z0-9_.]+)?-\d') { return $true }
    if ($leaf -match '(?i)^(bobiverse-|fr-\d|mrb-|uat-|docs-mrb-)') { return $true }
    if ($leaf -match '(?i)^[a-z][a-z0-9_.-]*-(wt-)?(fr|mrb|uat|docs-mrb|fix)-\d') { return $true }
    if ($leaf -match '(?i)^(bobiverse-|fr-|mrb-|uat-|docs-mrb-).*-wt$') { return $true }
    if ($leaf -match '(?i)^tmp-.*-(fr|mrb|uat)') { return $true }
    if ($full.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -and
        ($leaf -match '(?i)^(a-search|bobiverse|airc|jeeves|gh-jeeves)-') -and
        ($leaf -notmatch '(?i)-ref-\d')) {
        return $true
    }
    try {
        if (Get-Command Get-BobiverseJobWorktreeBase -ErrorAction SilentlyContinue) {
            $base = [IO.Path]::GetFullPath((Get-BobiverseJobWorktreeBase)).TrimEnd('\')
            if ($base -and $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
    } catch { }
    return $false
}

function Test-BobiverseSeatOnlyDirt([string]$PorcelainLine) {
    if (-not $PorcelainLine) { return $true }
    $rel = [string]$PorcelainLine
    if ($rel.Length -ge 3) { $rel = $rel.Substring(3).Trim() }
    if ($rel -match ' -> ') { $rel = ($rel -split ' -> ', 2)[-1].Trim() }
    $rel = $rel.Trim().Trim('"')
    if (-not $rel) { return $true }
    if ($rel -eq '.bobiverse-seat') { return $true }
    if ($rel -eq '.bob' -or $rel -like '.bob/*' -or $rel -like '.bob\*') { return $true }
    return $false
}

function Get-WorktreeLocalWorkState {
    <#
      FR #8023: tri-state result safe | has-work | unknown.
      Only safe is removable. has-work = porcelain dirt or unpushed HEAD.
      unknown = missing .git, status nonzero, HEAD unresolved, exception, locked.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$MergedHeadOid = ''
    )
    $result = [ordered]@{ State = 'unknown'; Reason = 'unknown' }
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        $result.Reason = 'missing-path'
        return [pscustomobject]$result
    }
    $gitDir = Join-Path $Path '.git'
    if (-not (Test-Path -LiteralPath $gitDir)) {
        $result.Reason = 'missing-git'
        return [pscustomobject]$result
    }
    try {
        if ($script:ClearLockedPaths) {
            $fullKey = [IO.Path]::GetFullPath($Path).TrimEnd('\')
            if ($script:ClearLockedPaths.ContainsKey($Path) -or $script:ClearLockedPaths.ContainsKey($fullKey)) {
                $result.Reason = 'locked'
                return [pscustomobject]$result
            }
        }
    } catch { }

    try {
        $head = & git -C $Path rev-parse HEAD 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $head) {
            $result.Reason = 'head-unresolved'
            return [pscustomobject]$result
        }
        $head = ([string]$head).Trim()
    } catch {
        $result.Reason = 'exception'
        return [pscustomobject]$result
    }

    try {
        $porcelain = @(& git -C $Path status --porcelain --ignore-submodules=none 2>$null | ForEach-Object { "$_" })
        if ($LASTEXITCODE -ne 0) {
            $result.Reason = 'status-failed'
            return [pscustomobject]$result
        }
        $meaningful = @($porcelain | Where-Object { -not (Test-BobiverseSeatOnlyDirt $_) })
        if ($meaningful.Count -gt 0) {
            $result.State = 'has-work'
            $result.Reason = 'dirty'
            return [pscustomobject]$result
        }
    } catch {
        $result.Reason = 'exception'
        return [pscustomobject]$result
    }

    try {
        if ($MergedHeadOid -and ($head -ieq $MergedHeadOid.Trim())) {
            $result.State = 'safe'
            $result.Reason = 'merged-head'
            return [pscustomobject]$result
        }
        if ($script:ClearFetchOk) {
            $contains = @()
            $containsExit = 1
            try {
                $contains = @(& git -C $Path for-each-ref --contains HEAD refs/remotes/origin 2>$null | ForEach-Object { "$_" })
                $containsExit = $LASTEXITCODE
            } catch {
                $contains = @()
                $containsExit = 1
            }
            if ($containsExit -eq 0 -and (@($contains | Where-Object { $_ }).Count -gt 0)) {
                $result.State = 'safe'
                $result.Reason = 'published'
                return [pscustomobject]$result
            }
            $result.State = 'has-work'
            $result.Reason = 'unpushed'
            return [pscustomobject]$result
        }
        $originUrl = $null
        $originExit = 1
        try {
            # Native stderr on missing origin must not become unknown (PS Stop).
            $originUrl = & git -C $Path remote get-url origin 2>$null
            $originExit = $LASTEXITCODE
        } catch {
            $originUrl = $null
            $originExit = 1
        }
        if ($originExit -eq 0 -and $originUrl) {
            $result.State = 'has-work'
            $result.Reason = 'unpushed'
            return [pscustomobject]$result
        }
        try {
            $unpushed = & git -C $Path rev-list --count '@{u}..HEAD' 2>$null
            if ($LASTEXITCODE -eq 0 -and [int]$unpushed -gt 0) {
                $result.State = 'has-work'
                $result.Reason = 'unpushed'
                return [pscustomobject]$result
            }
        } catch { }
        $result.State = 'safe'
        $result.Reason = 'local-clean'
        return [pscustomobject]$result
    } catch {
        $result.Reason = 'exception'
        return [pscustomobject]$result
    }
}

function Test-WorktreeHasLocalWork {
    param([Parameter(Mandatory)][string]$Path)
    $st = Get-WorktreeLocalWorkState -Path $Path
    return ($st.State -ne 'safe')
}

function Test-ProcessCitesPath([int]$ProcessId, [string]$FullPath) {
    if ($ProcessId -le 0 -or -not $FullPath) { return $false }
    try {
        $proc = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction SilentlyContinue
        if (-not $proc) { return $false }
        $cl = [string]$proc.CommandLine
        if ($cl -and $cl.IndexOf($FullPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    } catch { }
    return $false
}

function Test-WorktreeProtected {
    param(
        [Parameter(Mandatory = $false, Position = 0)]
        [string]$Path,
        [switch]$FullReclaim
    )
    if (-not $Path) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    } catch {
        return $false
    }
    $marker = Join-Path $full '.bobiverse-seat'
    if (Test-Path -LiteralPath $marker) {
        $seatPid = 0
        $parseOk = $false
        try {
            $raw = Get-Content -LiteralPath $marker -Raw -Encoding UTF8
            $obj = $raw | ConvertFrom-Json
            $parseOk = $true
            if ($obj.PSObject.Properties.Name -contains 'pid') {
                $seatPid = [int]$obj.pid
            }
        } catch {
            $parseOk = $false
            $seatPid = 0
        }
        if ($seatPid -gt 0) {
            $alive = Get-Process -Id $seatPid -ErrorAction SilentlyContinue
            if ($null -ne $alive) {
                if (Test-ProcessCitesPath -ProcessId $seatPid -FullPath $full) {
                    return $true
                }
            }
        }
        try {
            $mtime = (Get-Item -LiteralPath $marker).LastWriteTimeUtc
            $ageHours = ([datetime]::UtcNow - $mtime).TotalHours
            $staleHours = 48
            if ($null -ne $script:ClearStaleSeatHours) {
                $staleHours = [double]$script:ClearStaleSeatHours
            }
            if ($ageHours -lt $staleHours) {
                return $true
            }
            if (-not $parseOk) {
                return $false
            }
        } catch {
            return $true
        }
    }
    $selfPid = [int]$PID
    if ($null -eq $script:ClearToolProcs) {
        $script:ClearToolProcs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match '(?i)^(git|python|pyinstaller|py|pwsh|powershell)\.exe$' -and
                [int]$_.ProcessId -ne $selfPid
            })
    }
    foreach ($proc in @($script:ClearToolProcs)) {
        if ([int]$proc.ProcessId -eq $selfPid) { continue }
        $cl = [string]$proc.CommandLine
        if ($cl -and $cl.IndexOf($full, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $false
}

function Remove-BobiverseDeepWorktreeDirs {
    param([Parameter(Mandatory)][string]$WorktreePath)
    if (-not $WorktreePath -or -not (Test-Path -LiteralPath $WorktreePath)) { return }
    Get-ChildItem -LiteralPath $WorktreePath -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'cdk.out*' } |
        ForEach-Object {
            $target = $_.FullName
            Write-Host ("FR #3717 pre-rmdir deep tree {0}" -f $target)
            # FR #9500: Access denied must not abort Clear (same spirit as FR #4197).
            try {
                cmd.exe /c ('rmdir /s /q "' + $target + '"') 2>&1 | ForEach-Object {
                    if ($_ -is [System.Management.Automation.ErrorRecord]) { [void]$_.ToString() } else { "$_" }
                } | Out-Null
            } catch {
                Write-Warning ("FR #9500: cdk.out rmdir failed for {0}: {1}" -f $target, $_)
            }
        }
}

function Remove-BobiversePathForce {
    param([Parameter(Mandatory)][string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
    # FR #9500: Access denied on PYTEST~1 / .pytest_cache must not abort Clear
    # (StrictMode Stop + NativeCommandError from cmd stderr). Warn and continue
    # like FR #4197 missing-.git; optional attrib -R retry once.
    try {
        cmd.exe /c ('rmdir /s /q "' + $Path + '"') 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { [void]$_.ToString() } else { "$_" }
        } | Out-Null
    } catch {
        Write-Warning ("FR #9500: rmdir failed for {0}: {1}" -f $Path, $_)
    }
    if (Test-Path -LiteralPath $Path) {
        try {
            Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Name -match '(?i)^(PYTEST~1|\.pytest_cache)$' -or
                    $_.FullName -match '(?i)[\\/](\.pytest_cache|PYTEST~1)([\\/]|$)'
                } |
                ForEach-Object {
                    attrib.exe -R $_.FullName /S /D 2>$null | Out-Null
                }
        } catch { }
        try {
            cmd.exe /c ('rmdir /s /q "' + $Path + '"') 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { [void]$_.ToString() } else { "$_" }
            } | Out-Null
        } catch {
            Write-Warning ("FR #9500: rmdir retry failed for {0}; leaving in place and continuing: {1}" -f $Path, $_)
        }
    }
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-OrphanDirRemovable([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $items = @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop)
    } catch {
        return $false
    }
    if ($items.Count -eq 0) { return $true }
    foreach ($it in $items) {
        $n = [string]$it.Name
        if ($n -eq '.bobiverse-seat') { continue }
        if ($n -like 'cdk.out*') { continue }
        return $false
    }
    return $true
}

function Get-OwnerRepoFromOrigin([string]$RootFull) {
    try {
        $url = & git -C $RootFull remote get-url origin 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $url) { return '' }
        $u = [string]$url
        if ($u -match '(?i)github\.com[:/]+([^/]+)/([^/.]+)') {
            return ($Matches[1] + '/' + ($Matches[2] -replace '\.git$',''))
        }
        if ($u -match '(?i)^([^/]+)/([^/]+)$') {
            return ($Matches[1] + '/' + $Matches[2])
        }
    } catch { }
    return ''
}

function Get-JobKindNumberFromLeaf([string]$Leaf) {
    $out = [ordered]@{ Kind = ''; Number = 0 }
    if (-not $Leaf) { return [pscustomobject]$out }
    if ($Leaf -match '(?i)(?:^|-)(fr|mrb|fix|uat|docs-mrb)-(\d+)\b') {
        $k = $Matches[1].ToLowerInvariant()
        if ($k -eq 'docs-mrb') { $k = 'mrb' }
        $out.Kind = $k
        $out.Number = [int]$Matches[2]
    }
    return [pscustomobject]$out
}

function Get-JobGithubState {
    param(
        [string]$OwnerRepo,
        [string]$Kind,
        [int]$Number,
        [string]$BranchName = ''
    )
    $out = [ordered]@{
        State = 'unknown'
        HeadRefOid = ''
        ClosedOrMerged = $false
    }
    if (-not $OwnerRepo -or -not $Kind -or $Number -le 0) {
        return [pscustomobject]$out
    }
    if ($Kind -eq 'uat' -and $Number -eq 0) {
        return [pscustomobject]$out
    }
    $cacheKey = '{0}|{1}|{2}' -f $OwnerRepo, $Kind, $Number
    if ($script:ClearJobStateCache.ContainsKey($cacheKey)) {
        return $script:ClearJobStateCache[$cacheKey]
    }
    if ($script:ClearJobStateLookups -ge $script:ClearMaxJobStateLookups) {
        $script:ClearJobStateCache[$cacheKey] = [pscustomobject]$out
        return $script:ClearJobStateCache[$cacheKey]
    }
    $script:ClearJobStateLookups++
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        $script:ClearJobStateCache[$cacheKey] = [pscustomobject]$out
        return $script:ClearJobStateCache[$cacheKey]
    }
    try {
        if ($Kind -eq 'fr') {
            $json = & gh issue view $Number -R $OwnerRepo --json state 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $json) {
                $script:ClearJobStateCache[$cacheKey] = [pscustomobject]$out
                return $script:ClearJobStateCache[$cacheKey]
            }
            $obj = $json | ConvertFrom-Json
            $st = [string]$obj.state
            $out.State = $st
            if ($st -match '(?i)^closed$') {
                $out.ClosedOrMerged = $true
            }
            if ($BranchName) {
                $prJson = & gh pr list -R $OwnerRepo --head $BranchName --state merged --json headRefOid 2>$null
                if ($LASTEXITCODE -eq 0 -and $prJson) {
                    $prs = @($prJson | ConvertFrom-Json)
                    if ($prs.Count -gt 0 -and $prs[0].headRefOid) {
                        $out.HeadRefOid = [string]$prs[0].headRefOid
                    }
                }
            }
        } elseif ($Kind -eq 'mrb' -or $Kind -eq 'fix') {
            $json = & gh pr view $Number -R $OwnerRepo --json state,mergedAt,headRefOid 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $json) {
                $script:ClearJobStateCache[$cacheKey] = [pscustomobject]$out
                return $script:ClearJobStateCache[$cacheKey]
            }
            $obj = $json | ConvertFrom-Json
            $st = [string]$obj.state
            $out.State = $st
            if ($obj.headRefOid) { $out.HeadRefOid = [string]$obj.headRefOid }
            if ($st -match '(?i)^merged$' -or ($obj.mergedAt)) {
                $out.ClosedOrMerged = $true
            } elseif ($st -match '(?i)^closed$') {
                $out.ClosedOrMerged = $true
            }
        }
    } catch {
        $out.State = 'unknown'
        $out.ClosedOrMerged = $false
    }
    $script:ClearJobStateCache[$cacheKey] = [pscustomobject]$out
    return $script:ClearJobStateCache[$cacheKey]
}

function Get-ClearMutexName([string]$CommonDir) {
    $safe = ($CommonDir -replace '[^A-Za-z0-9]', '_')
    if ($safe.Length -gt 120) { $safe = $safe.Substring(0, 120) }
    return ('Global\Bobiverse-ClearJobWT-' + $safe)
}

function Enter-ClearMutex([string]$CommonDir) {
    $script:ClearMutex = $null
    $script:ClearMutexOwned = $false
    try {
        $name = Get-ClearMutexName $CommonDir
        $createdNew = $false
        $mtx = New-Object System.Threading.Mutex($false, $name, [ref]$createdNew)
        $owned = $mtx.WaitOne(0)
        if (-not $owned) {
            return $false
        }
        $script:ClearMutex = $mtx
        $script:ClearMutexOwned = $true
        return $true
    } catch {
        return $false
    }
}

function Exit-ClearMutex {
    if ($script:ClearMutexOwned -and $script:ClearMutex) {
        try { [void]$script:ClearMutex.ReleaseMutex() } catch { }
        try { $script:ClearMutex.Dispose() } catch { }
    }
    $script:ClearMutex = $null
    $script:ClearMutexOwned = $false
}

function Get-DiscoveredRepoRoots([string]$PrimaryRoot) {
    $roots = New-Object System.Collections.Generic.List[string]
    $add = {
        param($p)
        if (-not $p) { return }
        try {
            $full = [IO.Path]::GetFullPath($p).TrimEnd('\')
            if (-not (Test-Path -LiteralPath (Join-Path $full '.git'))) { return }
            foreach ($existing in $roots) {
                if ($existing -ieq $full) { return }
            }
            [void]$roots.Add($full)
        } catch { }
    }
    & $add $PrimaryRoot
    if (-not $DiscoverRepoRoots) {
        return @($roots.ToArray())
    }
    try {
        if (Get-Command Get-BobiverseJobWorktreeBase -ErrorAction SilentlyContinue) {
            $wtBase = [IO.Path]::GetFullPath((Get-BobiverseJobWorktreeBase)).TrimEnd('\')
            if ($wtBase -and (Test-Path -LiteralPath $wtBase)) {
                Get-ChildItem -LiteralPath $wtBase -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $repoDir = $_.FullName
                    Get-ChildItem -LiteralPath $repoDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                        $jobPath = $_.FullName
                        try {
                            $common = & git -C $jobPath rev-parse --git-common-dir 2>$null
                            if ($LASTEXITCODE -ne 0 -or -not $common) { return }
                            $commonFull = $common
                            if (-not [IO.Path]::IsPathRooted($commonFull)) {
                                $commonFull = [IO.Path]::GetFullPath((Join-Path $jobPath $common))
                            } else {
                                $commonFull = [IO.Path]::GetFullPath($commonFull)
                            }
                            if ($commonFull -match '(?i)[\\/]\.git([\\/]|$)') {
                                $repoRoot = $commonFull -replace '(?i)[\\/]\.git([\\/].*)?$', ''
                                & $add $repoRoot
                            }
                        } catch { }
                    }
                }
            }
        }
    } catch { }
    return @($roots.ToArray())
}

function Invoke-ClearOneRepoRoot {
    param(
        [Parameter(Mandatory)][string]$RootFull,
        [string]$KeepFull
    )

    $script:ClearFetchOk = $false
    $script:ClearLockedPaths = @{}
    $script:ClearJobStateCache = @{}
    $script:ClearJobStateLookups = 0
    $script:ClearMaxJobStateLookups = [Math]::Max(0, $MaxJobStateLookups)
    $script:ClearToolProcs = $null

    $counts = [ordered]@{
        removed = 0
        'kept-dirty' = 0
        'kept-unpushed' = 0
        'kept-unknown-git' = 0
        'kept-unknown-job' = 0
        'kept-active' = 0
        'kept-remove-failed' = 0
        'kept-unverifiable' = 0
        skipped_protected = 0
    }

    try {
        $commonDir = & git -C $RootFull rev-parse --git-common-dir 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $commonDir) {
            Write-Warning ("FR #8023: cannot resolve git-common-dir for {0}" -f $RootFull)
            return $counts
        }
        if (-not [IO.Path]::IsPathRooted($commonDir)) {
            $commonDir = [IO.Path]::GetFullPath((Join-Path $RootFull $commonDir))
        } else {
            $commonDir = [IO.Path]::GetFullPath($commonDir)
        }
    } catch {
        Write-Warning ("FR #8023: git-common-dir failed for {0}: {1}" -f $RootFull, $_)
        return $counts
    }

    if (-not (Enter-ClearMutex $commonDir)) {
        Write-Host 'skipped:busy'
        return $null
    }
    try {
        $freeGb = Get-FreeGB $RootFull
        Write-Host ("FreeGB={0} MinFreeGB={1} RepoRoot={2} KeepPath={3} StaleSeatHours={4} PruneClosedJobs={5}" -f `
            $freeGb, $MinFreeGB, $RootFull, $KeepFull, $StaleSeatHours, [bool]$PruneClosedJobs)

        $lowDisk = $Force -or ($freeGb -lt $MinFreeGB)

        try {
            $fetchOut = @(
                & git -C $RootFull fetch --prune origin 2>&1 |
                    ForEach-Object {
                        if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
                        else { "$_" }
                    }
            )
            if ($LASTEXITCODE -eq 0) {
                $script:ClearFetchOk = $true
            } else {
                Write-Warning ("FR #8023: git fetch --prune origin failed for {0}: {1}" -f $RootFull, ($fetchOut -join ' '))
                $script:ClearFetchOk = $false
            }
        } catch {
            Write-Warning ("FR #8023: git fetch --prune origin exception for {0}: {1}" -f $RootFull, $_)
            $script:ClearFetchOk = $false
        }

        if ($PruneClosedJobs -and -not $script:ClearFetchOk) {
            Write-Host ("FR #8023: fetch failed; skip prune for {0} (zero removals)" -f $RootFull)
            Write-Host ("Done removed=0 FreeGB_now={0} kept-dirty=0 kept-unpushed=0 kept-unknown-git=0 kept-unknown-job=0 kept-active=0 kept-remove-failed=0" -f (Get-FreeGB $RootFull))
            return $counts
        }

        $list = @(
            & git -C $RootFull worktree list --porcelain 2>&1 |
                ForEach-Object { "$_" } |
                Where-Object { $_ -ne '' }
        )
        if ($LASTEXITCODE -ne 0) {
            throw "git worktree list failed: $($list -join "`n")"
        }

        $paths = New-Object System.Collections.Generic.List[string]
        $currentWt = ''
        foreach ($line in $list) {
            if ($line -match '^worktree (.+)$') {
                $currentWt = $Matches[1]
                [void]$paths.Add($currentWt)
            } elseif ($line -match '^locked' -and $currentWt) {
                try {
                    $lk = [IO.Path]::GetFullPath($currentWt).TrimEnd('\')
                    $script:ClearLockedPaths[$lk] = $true
                    $script:ClearLockedPaths[$currentWt] = $true
                } catch {
                    $script:ClearLockedPaths[$currentWt] = $true
                }
            }
        }

        $ownerRepo = Get-OwnerRepoFromOrigin $RootFull
        $jobTrees = @($paths.ToArray() | Where-Object { Test-IsJobWorktreePath $_ $RootFull $KeepFull })
        $jobTrees = @($jobTrees | Sort-Object {
            if (Test-Path -LiteralPath $_) {
                (Get-Item -LiteralPath $_).LastWriteTimeUtc
            } else {
                [datetime]::MinValue
            }
        })

        $candidates = New-Object System.Collections.Generic.List[string]
        $protectedTrees = New-Object System.Collections.Generic.List[string]

        foreach ($wt in $jobTrees) {
            $wtFull = $wt
            try { $wtFull = [IO.Path]::GetFullPath($wt).TrimEnd('\') } catch { }

            if (Test-WorktreeProtected -Path $wt -FullReclaim:$lowDisk) {
                Write-Host "FR #2727/#4988 skip protected worktree $wt"
                $counts['kept-active']++
                $counts.skipped_protected++
                [void]$protectedTrees.Add($wt)
                continue
            }

            $leaf = Split-Path -Leaf $wtFull
            $kindNum = Get-JobKindNumberFromLeaf $leaf
            $mergedOid = ''
            $jobClosed = $false
            $jobUnknown = $false

            if ($PruneClosedJobs) {
                $markerRepo = ''
                $markerPath = Join-Path $wtFull '.bobiverse-seat'
                if (Test-Path -LiteralPath $markerPath) {
                    try {
                        $mobj = (Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8) | ConvertFrom-Json
                        if ($mobj.PSObject.Properties.Name -contains 'repo') {
                            $markerRepo = [string]$mobj.repo
                        }
                    } catch { }
                }
                $lookupRepo = $ownerRepo
                if (-not $lookupRepo -and $markerRepo) {
                    # Local bare origins (fixtures) may not parse; marker repo is authoritative then.
                    $lookupRepo = $markerRepo
                }
                if ($markerRepo -and $ownerRepo -and ($markerRepo -ine $ownerRepo)) {
                    $jobUnknown = $true
                } elseif (-not $kindNum.Kind -or $kindNum.Number -le 0) {
                    $jobUnknown = $true
                } elseif (-not $lookupRepo) {
                    $jobUnknown = $true
                } else {
                    $branchName = ''
                    try {
                        $branchName = (& git -C $wtFull rev-parse --abbrev-ref HEAD 2>$null)
                        if ($LASTEXITCODE -ne 0) { $branchName = '' }
                        $branchName = ([string]$branchName).Trim()
                        if ($branchName -eq 'HEAD') { $branchName = '' }
                    } catch { $branchName = '' }
                    $ghState = Get-JobGithubState -OwnerRepo $lookupRepo -Kind $kindNum.Kind -Number $kindNum.Number -BranchName $branchName
                    if ($ghState.State -eq 'unknown') {
                        $jobUnknown = $true
                    } elseif (-not $ghState.ClosedOrMerged) {
                        Write-Host ("FR #8023 keep open job {0} state={1}" -f $wt, $ghState.State)
                        $counts['kept-active']++
                        continue
                    } else {
                        $jobClosed = $true
                        $mergedOid = $ghState.HeadRefOid
                    }
                }
                if ($jobUnknown) {
                    Write-Host ("FR #8023 keep unknown-job {0}" -f $wt)
                    $counts['kept-unknown-job']++
                    continue
                }
                if (-not $jobClosed) {
                    $counts['kept-active']++
                    continue
                }
            }

            $st = Get-WorktreeLocalWorkState -Path $wt -MergedHeadOid $mergedOid
            if ($st.State -eq 'safe') {
                [void]$candidates.Add($wt)
            } elseif ($st.State -eq 'has-work') {
                if ($st.Reason -eq 'dirty') {
                    Write-Host ("FR #8023 keep dirty worktree {0}" -f $wt)
                    $counts['kept-dirty']++
                } else {
                    Write-Host ("FR #8023 keep unpushed worktree {0}" -f $wt)
                    $counts['kept-unpushed']++
                }
                [void]$protectedTrees.Add($wt)
            } else {
                Write-Host ("FR #8023 keep unknown-git worktree {0} reason={1}" -f $wt, $st.Reason)
                $counts['kept-unknown-git']++
                [void]$protectedTrees.Add($wt)
            }
        }

        $toRemove = @()
        if ($PruneClosedJobs) {
            $toRemove = @($candidates)
            Write-Host ("FR #8023 PruneClosedJobs: removing {0} closed/merged safe worktree(s)" -f @($toRemove).Count)
        } else {
            $jobTreeCount = @($candidates).Count
            $softCapNeeded = ($MaxExtraJobTrees -ge 0 -and $jobTreeCount -gt $MaxExtraJobTrees)
            if (-not $lowDisk -and -not $softCapNeeded) {
                Write-Host "OK: free space above MinFreeGB and job-tree count within MaxExtraJobTrees; pass -Force to prune anyway."
                if ($counts.skipped_protected -gt 0) {
                    Write-Host ("FR #2727 skipped_protected={0}" -f $counts.skipped_protected)
                }
                Write-Host ("Done removed={0} FreeGB_now={1} kept-dirty={2} kept-unpushed={3} kept-unknown-git={4} kept-unknown-job={5} kept-active={6} kept-remove-failed={7}" -f `
                    0, (Get-FreeGB $RootFull), $counts['kept-dirty'], $counts['kept-unpushed'], $counts['kept-unknown-git'], $counts['kept-unknown-job'], $counts['kept-active'], $counts['kept-remove-failed'])
                return $counts
            }
            if ($lowDisk) {
                $toRemove = @($candidates)
                Write-Host ("FR #1661 full reclaim: lowDisk/Force removing {0} job worktree(s)" -f @($toRemove).Count)
            } elseif ($softCapNeeded) {
                $sorted = @($candidates | Sort-Object {
                    if (Test-Path -LiteralPath $_) {
                        (Get-Item -LiteralPath $_).LastWriteTimeUtc
                    } else {
                        [datetime]::MinValue
                    }
                })
                $sortedCount = @($sorted).Count
                $toRemove = @($sorted | Select-Object -First ([Math]::Max(0, $sortedCount - $MaxExtraJobTrees)))
                Write-Host ("FR #1661 earlier prune / soft cap: removing {0} extra job worktree(s) (MaxExtraJobTrees={1})" -f @($toRemove).Count, $MaxExtraJobTrees)
            }
        }

        foreach ($p in $toRemove) {
            if ($WhatIfPreference) {
                Write-Host "WhatIf: git worktree remove $p"
                $counts.removed++
                continue
            }
            if (-not $PSCmdlet.ShouldProcess($p, 'git worktree remove')) { continue }

            if (Test-WorktreeProtected -Path $p -FullReclaim:$lowDisk) {
                Write-Host ("FR #8023 recheck: now protected, skip {0}" -f $p)
                $counts['kept-active']++
                continue
            }
            $st2 = Get-WorktreeLocalWorkState -Path $p
            if ($st2.State -ne 'safe') {
                Write-Host ("FR #8023 recheck: state={0} reason={1}, skip {2}" -f $st2.State, $st2.Reason, $p)
                if ($st2.State -eq 'has-work' -and $st2.Reason -eq 'dirty') { $counts['kept-dirty']++ }
                elseif ($st2.State -eq 'has-work') { $counts['kept-unpushed']++ }
                else { $counts['kept-unknown-git']++ }
                continue
            }

            Write-Host "Removing worktree $p"
            # Contiguous pin (FR #4197 / MRB #4198): Write-Warning ("FR #4197: worktree path or .git missing for {0}; rmdir/prune and continue"
            # One broken registration must not abort the rest of the Clear run. FR #2460 + FR #4197.

            $gitMarker = Join-Path $p '.git'
            if (-not (Test-Path -LiteralPath $p)) {
                Write-Warning ("FR #4197: worktree path missing for {0}; prune metadata and continue" -f $p)
                continue
            }
            if (-not (Test-Path -LiteralPath $gitMarker)) {
                Write-Warning ("FR #4197/#8023: .git missing for {0}; keep as unknown and continue" -f $p)
                $counts['kept-unknown-git']++
                continue
            }

            Remove-BobiverseDeepWorktreeDirs -WorktreePath $p
            # FR #6563 / #8023: seat marker is not "local work", but git worktree
            # remove without --force still refuses untracked .bobiverse-seat / .bob/.
            # Drop those markers only after the fail-closed predicate said safe.
            try {
                $seatMark = Join-Path $p '.bobiverse-seat'
                if (Test-Path -LiteralPath $seatMark) {
                    Remove-Item -LiteralPath $seatMark -Force -ErrorAction SilentlyContinue
                }
                $bobDir = Join-Path $p '.bob'
                if (Test-Path -LiteralPath $bobDir) {
                    Remove-Item -LiteralPath $bobDir -Recurse -Force -ErrorAction SilentlyContinue
                }
            } catch { }
            $gitExit = 0
            $gitOut = @()
            try {
                $gitOut = @(
                    # pin: & git -C $rootFull worktree remove (RootFull param)
                    & git -C $RootFull worktree remove $p 2>&1 |
                        ForEach-Object {
                            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
                            else { "$_" }
                        }
                )
                $gitExit = $LASTEXITCODE
            } catch {
                $gitExit = 1
                $gitOut = @("$_")
            }
            foreach ($line in $gitOut) {
                if ($line) { Write-Host $line }
            }
            if ($gitExit -ne 0) {
                Write-Warning ("FR #8023: worktree remove failed for {0}; keeping dir (kept-remove-failed)" -f $p)
                $counts['kept-remove-failed']++
                continue
            }
            if (Test-Path -LiteralPath $p) {
                Write-Warning ("FR #8023: path still present after git remove for {0}; keeping (kept-remove-failed; no Remove-Item fallback)" -f $p)
                $counts['kept-remove-failed']++
                continue
            }
            $counts.removed++
        }

        $tempRoot = $env:TEMP
        if ($lowDisk -and $tempRoot -and (Test-Path -LiteralPath $tempRoot) -and -not $PruneClosedJobs) {
            $orphanFilters = @('bobiverse-*', 'a-search-*', 'airc-*', 'jeeves-*', 'gh-jeeves-*')
            foreach ($ofilter in $orphanFilters) {
                Get-ChildItem -LiteralPath $tempRoot -Directory -Filter $ofilter -ErrorAction SilentlyContinue | ForEach-Object {
                    $full = $_.FullName
                    if ($KeepFull -and ($full.TrimEnd('\') -ieq $KeepFull.TrimEnd('\'))) { return }
                    if (-not (Test-IsJobWorktreePath $full $RootFull $KeepFull)) { return }
                    if (Test-IsOperatorOrNonJobLeaf (Split-Path -Leaf $full)) { return }
                    if (Test-WorktreeProtected -Path $full -FullReclaim:$lowDisk) { return }
                    $gitFile = Join-Path $full '.git'
                    if (Test-Path -LiteralPath $gitFile) {
                        try {
                            $gi = Get-Item -LiteralPath $gitFile
                            if ($gi.PSIsContainer) {
                                Write-Host ("FR #8023 skip orphan with .git {0}" -f $full)
                                $counts['kept-unverifiable']++
                                return
                            }
                            $gitContent = Get-Content -LiteralPath $gitFile -Raw -ErrorAction SilentlyContinue
                            if ($gitContent -match 'gitdir:\s*(.+)') {
                                $gd = $Matches[1].Trim()
                                if ($gd -and (Test-Path -LiteralPath $gd)) {
                                    Write-Host ("FR #8023 skip orphan linked to live gitdir {0}" -f $full)
                                    $counts['kept-unverifiable']++
                                    return
                                }
                            }
                        } catch {
                            $counts['kept-unverifiable']++
                            return
                        }
                    }
                    $stillListed = $false
                    foreach ($pp in $paths) {
                        try {
                            if ([IO.Path]::GetFullPath($pp).TrimEnd('\') -ieq $full.TrimEnd('\')) { $stillListed = $true; break }
                        } catch { }
                    }
                    if ($stillListed) { return }
                    if (-not (Test-OrphanDirRemovable $full)) {
                        Write-Host ("FR #8023 keep unverifiable orphan {0}" -f $full)
                        $counts['kept-unverifiable']++
                        return
                    }
                    if ($WhatIfPreference) {
                        Write-Host "WhatIf: Remove-Item orphan $full"
                        $counts.removed++
                        return
                    }
                    if ($PSCmdlet.ShouldProcess($full, "Remove orphan $ofilter directory")) {
                        Write-Host "Removing orphan $full"
                        Remove-BobiversePathForce -Path $full
                        if (-not (Test-Path -LiteralPath $full)) { $counts.removed++ }
                    }
                }
            }
        }

        if ($lowDisk -and -not $PruneClosedJobs -and (Get-Command Get-BobiverseJobWorktreeBase -ErrorAction SilentlyContinue)) {
            try {
                $wtBase = [IO.Path]::GetFullPath((Get-BobiverseJobWorktreeBase)).TrimEnd('\')
            } catch { $wtBase = '' }
            if ($wtBase -and (Test-Path -LiteralPath $wtBase)) {
                Get-ChildItem -LiteralPath $wtBase -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $repoDir = $_.FullName
                    Get-ChildItem -LiteralPath $repoDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                        $full = $_.FullName
                        if ($KeepFull -and ($full.TrimEnd('\') -ieq $KeepFull.TrimEnd('\'))) { return }
                        if (-not (Test-IsJobWorktreePath $full $RootFull $KeepFull)) { return }
                        if (Test-WorktreeProtected -Path $full -FullReclaim:$lowDisk) { return }
                        $stillListed = $false
                        foreach ($pp in $paths) {
                            try {
                                if ([IO.Path]::GetFullPath($pp).TrimEnd('\') -ieq $full.TrimEnd('\')) { $stillListed = $true; break }
                            } catch { }
                        }
                        if ($stillListed) { return }
                        $gitFile = Join-Path $full '.git'
                        if (Test-Path -LiteralPath $gitFile) {
                            Write-Host ("FR #8023 keep base orphan with .git {0}" -f $full)
                            $counts['kept-unverifiable']++
                            return
                        }
                        if (-not (Test-OrphanDirRemovable $full)) {
                            Write-Host ("FR #8023 keep unverifiable base orphan {0}" -f $full)
                            $counts['kept-unverifiable']++
                            return
                        }
                        if ($WhatIfPreference) {
                            Write-Host "WhatIf: Remove-Item FR #4988 base orphan $full"
                            $counts.removed++
                            return
                        }
                        if ($PSCmdlet.ShouldProcess($full, 'Remove FR #4988 job-worktree-base orphan')) {
                            Write-Host "Removing FR #4988 base orphan $full"
                            Remove-BobiversePathForce -Path $full
                            if (-not (Test-Path -LiteralPath $full)) { $counts.removed++ }
                        }
                    }
                }
            }
        }

        if ($counts.removed -gt 0 -or $Force) {
            if ($WhatIfPreference) {
                Write-Host "WhatIf: git worktree prune"
            } else {
                Write-Host "Pruning worktree metadata"
                $pruneOut = @()
                $pruneExit = 0
                try {
                    $pruneOut = @(
                        # pin: & git -C $rootFull worktree prune
            & git -C $RootFull worktree prune 2>&1 |
                            ForEach-Object {
                                if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() }
                                else { "$_" }
                            }
                    )
                    $pruneExit = $LASTEXITCODE
                } catch {
                    $pruneOut = @("$_")
                    $pruneExit = 1
                    Write-Warning ("FR #4197: git worktree prune failed (continuing): {0}" -f $_)
                }
                if ($pruneExit -ne 0) {
                    Write-Warning ("FR #8023: git worktree prune exit={0}" -f $pruneExit)
                }
                foreach ($line in $pruneOut) {
                    if ($line) { Write-Host $line }
                }
            }
        }

        $freeAfter = Get-FreeGB $RootFull
        Write-Host ("Done removed={0} FreeGB_now={1} kept-dirty={2} kept-unpushed={3} kept-unknown-git={4} kept-unknown-job={5} kept-active={6} kept-remove-failed={7} skipped_protected={8}" -f `
            $counts.removed, $freeAfter, $counts['kept-dirty'], $counts['kept-unpushed'], $counts['kept-unknown-git'], $counts['kept-unknown-job'], $counts['kept-active'], $counts['kept-remove-failed'], $counts.skipped_protected)

        if (($freeAfter -lt $MinFreeGB) -and (-not $WhatIfPreference) -and (-not $SkipSeatDisk)) {
            $seatDisk = $SeatDiskScript
            if (-not $seatDisk -and $PSScriptRoot) {
                $seatDisk = Join-Path $PSScriptRoot 'Clear-BobiverseSeatDisk.ps1'
            }
            if ($seatDisk -and (Test-Path -LiteralPath $seatDisk)) {
                Write-Host ("FR #7479: FreeGB={0} still below MinFreeGB={1}; running Clear-BobiverseSeatDisk -Reclaim (protected worktrees stay)" -f $freeAfter, $MinFreeGB)
                & $seatDisk -Reclaim -MinFreeGB $MinFreeGB
                if (-not $?) {
                    Write-Warning 'FR #7479: Clear-BobiverseSeatDisk -Reclaim failed'
                }
                $freeAfter = Get-FreeGB $RootFull
                Write-Host ("FR #7479 SeatDisk FreeGB_now={0}" -f $freeAfter)
            }
        }
        if ($freeAfter -lt $MinFreeGB) {
            $rootDrive = [System.IO.Path]::GetPathRoot($RootFull).TrimEnd('\').TrimEnd(':')
            $otherVol = 0
            foreach ($pt in $protectedTrees) {
                try {
                    $pd = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($pt)).TrimEnd('\').TrimEnd(':')
                    if ($pd -and ($pd -ine $rootDrive)) { $otherVol++ }
                } catch { }
            }
            Write-Warning ("FR #3698 / FR #4192 / FR #4212: RepoRoot drive FreeGB={0} still below MinFreeGB={1} after reclaim (removed={2}, skipped_protected={3}, skipped_other_volume={4}). Job trees on another volume do not free this drive. Next: run Clear-BobiverseSeatDisk.ps1 -Reclaim -KeepSessionId <this-session> (optional -IncludeAiBackups) for ~/.grok / pip/npm / aged user-%TEMP% / aged .cursor/chats caches; only then file a disk-capacity intake or put the job tree on a roomy drive. Never hand-delete C:\ai\* wt trees (FR #2727)." -f $freeAfter, $MinFreeGB, $counts.removed, $counts.skipped_protected, $otherVol)
        }
        return $counts
    } finally {
        Exit-ClearMutex
    }
}

if (-not $RepoRoot) {
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

$script:ClearStaleSeatHours = [double]$StaleSeatHours
$script:ClearToolProcs = $null

$allRoots = @(Get-DiscoveredRepoRoots $rootFull)
foreach ($r in $allRoots) {
    $result = Invoke-ClearOneRepoRoot -RootFull $r -KeepFull $keepFull
    if ($null -eq $result) {
        exit 0
    }
}
