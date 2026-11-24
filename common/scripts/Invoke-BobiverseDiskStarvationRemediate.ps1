<#
.SYNOPSIS
  Token-free disk-starvation remediator for one fleet machine (monitor disk_starvation).

.DESCRIPTION
  Safe-scope reclaim when worktree-create-failed:disk / disk-low starves seats:
    1) FreeGB before on C:
    2) Clear-BobiverseJobWorktrees -Force for known product installs (bob, a-search, jeeves, airc)
    3) Clear-BobiverseSeatDisk -Reclaim -Force
    4) Orphan bob-bridge worktree leaves under Users\*\.grok\bob-bridge\worktrees (flamingo class #9692)
    5) FreeGB after

  Runs locally when -Machine matches this host; otherwise WinRM Invoke-Command to -Machine.
  Never touches Ergo / BobIrcd / live seat processes / install roots themselves.
  Never invents hand Remove-Item of arbitrary C:\ai\* trees (FR #2727) beyond Clear helpers
  and orphan bob-bridge job leaves.

.PARAMETER Machine
  Fleet machine id (lowercase hostname), e.g. flamingo.

.PARAMETER MinFreeGB
  Target free space after reclaim (default 8).

.PARAMETER DryRun
  Probe FreeGB / list candidates only; no deletes.

.PARAMETER LocalOnly
  Refuse WinRM; only run when this host is -Machine.

.OUTPUTS
  One JSON object on stdout: machine, free_gb_before, free_gb_after, actions[], ok, error.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Machine,
    [double]$MinFreeGB = 8,
    [switch]$DryRun,
    [switch]$LocalOnly,
    [string]$AiRoot = 'C:\ai'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Get-BobMachineId {
    $raw = if ($env:BOB_MACHINE_ID) { $env:BOB_MACHINE_ID } else { $env:COMPUTERNAME }
    return (($raw + '') -replace '[^A-Za-z0-9]+', '').ToLowerInvariant()
}

function Get-CFreeGB {
    try {
        $d = Get-PSDrive -Name C -ErrorAction Stop
        return [math]::Round(([double]$d.Free) / 1GB, 3)
    } catch {
        return $null
    }
}

function Resolve-ClearScripts {
    $cands = @(
        (Join-Path $AiRoot 'bob\common\scripts'),
        (Join-Path $AiRoot 'bob\scripts'),
        (Join-Path $PSScriptRoot '.'),
        (Join-Path $AiRoot 'jeeves\common\scripts')
    )
    $clear = $null
    $seat = $null
    foreach ($dir in $cands) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        $c = Join-Path $dir 'Clear-BobiverseJobWorktrees.ps1'
        $s = Join-Path $dir 'Clear-BobiverseSeatDisk.ps1'
        if (-not $clear -and (Test-Path -LiteralPath $c)) { $clear = $c }
        if (-not $seat -and (Test-Path -LiteralPath $s)) { $seat = $s }
    }
    return @{ Clear = $clear; Seat = $seat }
}

function Invoke-LocalRemediate {
    param([double]$MinFreeGB, [switch]$DryRun)

    $actions = New-Object System.Collections.Generic.List[object]
    $before = Get-CFreeGB
    $scripts = Resolve-ClearScripts

    $repoRoots = @(
        (Join-Path $AiRoot 'bob'),
        (Join-Path $AiRoot 'a-search'),
        (Join-Path $AiRoot 'jeeves'),
        (Join-Path $AiRoot 'airc')
    ) | Where-Object { Test-Path -LiteralPath $_ }

    if ($DryRun) {
        $actions.Add(@{ step = 'dry_run'; free_gb = $before; repos = @($repoRoots); clear = $scripts.Clear; seat = $scripts.Seat })
        return @{
            ok              = $true
            dry_run         = $true
            free_gb_before  = $before
            free_gb_after   = $before
            actions         = @($actions)
            min_free_gb     = $MinFreeGB
        }
    }

    foreach ($root in $repoRoots) {
        if (-not $scripts.Clear) { break }
        try {
            $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scripts.Clear -RepoRoot $root -Force -MinFreeGB $MinFreeGB 2>&1 | Out-String
            $actions.Add(@{ step = 'Clear-BobiverseJobWorktrees'; repo = $root; ok = $true; detail = $out.Substring(0, [Math]::Min(400, $out.Length)) })
        } catch {
            $actions.Add(@{ step = 'Clear-BobiverseJobWorktrees'; repo = $root; ok = $false; error = $_.Exception.Message })
        }
    }

    if ($scripts.Seat) {
        try {
            $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scripts.Seat -Reclaim -Force -MinFreeGB $MinFreeGB 2>&1 | Out-String
            $actions.Add(@{ step = 'Clear-BobiverseSeatDisk'; ok = $true; detail = $out.Substring(0, [Math]::Min(400, $out.Length)) })
        } catch {
            $actions.Add(@{ step = 'Clear-BobiverseSeatDisk'; ok = $false; error = $_.Exception.Message })
        }
    } else {
        $actions.Add(@{ step = 'Clear-BobiverseSeatDisk'; ok = $false; error = 'script_missing' })
    }

    # Orphan bob-bridge worktrees (not always registered with git worktree list).
    $bridgeRemoved = 0
    $bridgeBytes = [int64]0
    foreach ($userDir in @(Get-ChildItem -Path 'C:\Users' -Directory -ErrorAction SilentlyContinue)) {
        $bridge = Join-Path $userDir.FullName '.grok\bob-bridge\worktrees'
        if (-not (Test-Path -LiteralPath $bridge)) { continue }
        foreach ($repoLeaf in @(Get-ChildItem -LiteralPath $bridge -Directory -ErrorAction SilentlyContinue)) {
            foreach ($leaf in @(Get-ChildItem -LiteralPath $repoLeaf.FullName -Directory -ErrorAction SilentlyContinue)) {
                if ($leaf.Name -notmatch '^(fr|mrb|fix|uat|job)-') { continue }
                $marker = Join-Path $leaf.FullName '.bobiverse-seat'
                if (Test-Path -LiteralPath $marker) {
                    try {
                        $ageH = ((Get-Date) - (Get-Item -LiteralPath $marker).LastWriteTime).TotalHours
                        if ($ageH -lt 48) { continue }
                    } catch { continue }
                }
                try {
                    $size = (Get-ChildItem -LiteralPath $leaf.FullName -Recurse -Force -ErrorAction SilentlyContinue |
                        Measure-Object -Property Length -Sum).Sum
                    if (-not $size) { $size = 0 }
                    cmd /c "rmdir /s /q `"$($leaf.FullName)`"" | Out-Null
                    if (-not (Test-Path -LiteralPath $leaf.FullName)) {
                        $bridgeRemoved++
                        $bridgeBytes += [int64]$size
                    }
                } catch { }
            }
        }
    }
    $actions.Add(@{
            step           = 'orphan_bob_bridge_worktrees'
            removed        = $bridgeRemoved
            approx_bytes   = $bridgeBytes
            approx_gb      = [math]::Round($bridgeBytes / 1GB, 3)
        })

    $after = Get-CFreeGB
    $ok = ($null -ne $after) -and ($after -ge $MinFreeGB)
    return @{
        ok             = [bool]$ok
        dry_run        = $false
        free_gb_before = $before
        free_gb_after  = $after
        actions        = @($actions)
        min_free_gb    = $MinFreeGB
        target_met     = [bool]$ok
    }
}

$mach = (($Machine + '') -replace '[^A-Za-z0-9]+', '').ToLowerInvariant()
if (-not $mach) { throw 'Machine is empty after sanitize' }

$local = Get-BobMachineId
$result = $null

if ($local -eq $mach) {
    $result = Invoke-LocalRemediate -MinFreeGB $MinFreeGB -DryRun:$DryRun
    $result.machine = $mach
    $result.via = 'local'
} elseif ($LocalOnly) {
    $result = @{
        ok      = $false
        machine = $mach
        via     = 'skipped_not_local'
        error   = "host=$local is not machine=$mach and -LocalOnly set"
        findings = @("disk remediator skipped: not local host")
    }
} else {
    try {
        $sb = {
            param($MinFreeGB, $DryRun, $AiRoot, $ScriptText)
            $tmp = Join-Path $env:TEMP ('bob-disk-remediate-' + [guid]::NewGuid().ToString('n') + '.ps1')
            # Remote hosts already have Clear scripts under C:\ai\bob\common\scripts;
            # run an inline local body instead of shipping this file.
            $before = $null
            try { $before = [math]::Round(((Get-PSDrive C).Free) / 1GB, 3) } catch { }
            if ($DryRun) {
                return @{ ok = $true; dry_run = $true; free_gb_before = $before; free_gb_after = $before; actions = @(@{ step = 'dry_run_remote' }); machine = $env:COMPUTERNAME }
            }
            $clear = 'C:\ai\bob\common\scripts\Clear-BobiverseJobWorktrees.ps1'
            $seat = 'C:\ai\bob\common\scripts\Clear-BobiverseSeatDisk.ps1'
            $actions = @()
            foreach ($root in @('C:\ai\bob', 'C:\ai\a-search', 'C:\ai\jeeves', 'C:\ai\airc')) {
                if (-not (Test-Path $root)) { continue }
                if (-not (Test-Path $clear)) { continue }
                try {
                    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $clear -RepoRoot $root -Force -MinFreeGB $MinFreeGB 2>&1 | Out-Null
                    $actions += @{ step = 'Clear-BobiverseJobWorktrees'; repo = $root; ok = $true }
                } catch {
                    $actions += @{ step = 'Clear-BobiverseJobWorktrees'; repo = $root; ok = $false; error = $_.Exception.Message }
                }
            }
            if (Test-Path $seat) {
                try {
                    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $seat -Reclaim -Force -MinFreeGB $MinFreeGB 2>&1 | Out-Null
                    $actions += @{ step = 'Clear-BobiverseSeatDisk'; ok = $true }
                } catch {
                    $actions += @{ step = 'Clear-BobiverseSeatDisk'; ok = $false; error = $_.Exception.Message }
                }
            }
            $bridgeRemoved = 0
            Get-ChildItem C:\Users -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $bridge = Join-Path $_.FullName '.grok\bob-bridge\worktrees'
                if (-not (Test-Path $bridge)) { return }
                Get-ChildItem $bridge -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                        if ($_.Name -notmatch '^(fr|mrb|fix|uat|job)-') { return }
                        $marker = Join-Path $_.FullName '.bobiverse-seat'
                        if (Test-Path $marker) {
                            try {
                                if (((Get-Date) - (Get-Item $marker).LastWriteTime).TotalHours -lt 48) { return }
                            } catch { return }
                        }
                        cmd /c "rmdir /s /q `"$($_.FullName)`"" | Out-Null
                        if (-not (Test-Path $_.FullName)) { $script:bridgeRemoved++ }
                    }
                }
            }
            $actions += @{ step = 'orphan_bob_bridge_worktrees'; removed = $bridgeRemoved }
            $after = $null
            try { $after = [math]::Round(((Get-PSDrive C).Free) / 1GB, 3) } catch { }
            return @{
                ok             = ($null -ne $after -and $after -ge $MinFreeGB)
                dry_run        = $false
                free_gb_before = $before
                free_gb_after  = $after
                actions        = $actions
                min_free_gb    = $MinFreeGB
                target_met     = ($null -ne $after -and $after -ge $MinFreeGB)
            }
        }
        $remote = Invoke-Command -ComputerName $mach -ScriptBlock $sb -ArgumentList @($MinFreeGB, [bool]$DryRun, $AiRoot, '') -ErrorAction Stop
        # Remoting deserializes hashtables oddly; rebuild a plain local hashtable.
        $result = @{
            machine = $mach
            via     = 'winrm'
        }
        if ($remote -is [hashtable]) {
            foreach ($k in @($remote.Keys)) { $result[$k] = $remote[$k] }
        } elseif ($null -ne $remote) {
            foreach ($p in @($remote.PSObject.Properties)) {
                if ($p.Name -in @('PSComputerName', 'RunspaceId', 'PSShowComputerName')) { continue }
                $result[$p.Name] = $p.Value
            }
        }
        $result['machine'] = $mach
        $result['via'] = 'winrm'
    } catch {
        $result = @{
            ok       = $false
            machine  = $mach
            via      = 'winrm'
            error    = $_.Exception.Message
            findings = @("WinRM remediator failed for $mach")
        }
    }
}

# Prefer pscustomobject so ConvertTo-Json emits a JSON object (not Keys/Values).
$outObj = New-Object psobject
foreach ($k in @($result.Keys)) {
    Add-Member -InputObject $outObj -MemberType NoteProperty -Name $k -Value $result[$k] -Force
}
$outObj | ConvertTo-Json -Depth 6 -Compress
$okFlag = $false
if ($result.ContainsKey('ok')) { $okFlag = [bool]$result['ok'] }
if (-not $okFlag) { exit 1 }
exit 0
