#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7233: pick bob-ear.exe vs python irc_agent.py without comparing file mtimes.
.NOTES
  Installed bob-ear.exe always wins when present. Python only when the exe is
  missing or BOB_EAR_PYTHON is 1/true/yes (dev/hotpatch fallback). Logs SHA-256
  plus ear-component source_commit and VERSION when those files exist.
  FR #7300 / mrb-7311-fix: source= reads ear sidecars next to bob-ear.exe
  (provenance.txt / manifest.txt / MANIFEST.json). Never install-root MANIFEST.
#>

function Get-BobEarSourceCommitFromProvenance {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    $source = ''; $workflow = ''; $commit = ''
    try {
        foreach ($line in @(Get-Content -LiteralPath $Path -ErrorAction Stop)) {
            if (-not $line) { continue }
            $eq = $line.IndexOf('=')
            if ($eq -le 0) { continue }
            $k = $line.Substring(0, $eq).Trim().ToLowerInvariant()
            $v = $line.Substring($eq + 1).Trim()
            if (-not $v) { continue }
            # Accept 7-40 hex (CI full SHA or short).
            if ($v -notmatch '^[0-9a-fA-F]{7,40}$') { continue }
            switch ($k) {
                'source_commit' { if (-not $source) { $source = $v } }
                'workflow_commit' { if (-not $workflow) { $workflow = $v } }
                'commit' { if (-not $commit) { $commit = $v } }
            }
        }
    } catch { }
    if ($source) { return $source }
    if ($workflow) { return $workflow }
    return $commit
}

function Get-BobEarSourceCommitFromJson {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    try {
        $j = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($k in @('source_commit', 'workflow_commit', 'commit')) {
            $v = [string]$j.$k
            if ($v -and $v.Trim()) { return $v.Trim() }
        }
    } catch { }
    return ''
}

function Select-BobEarLaunch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ScriptDir,
        [string]$InstallRoot = ''
    )
    if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $ScriptDir }
    $earExe = Join-Path $ScriptDir 'bob-ear.exe'
    $agent = Join-Path $ScriptDir 'irc_agent.py'
    $envPy = ''
    try { $envPy = [string]$env:BOB_EAR_PYTHON } catch { $envPy = '' }
    $wantPy = ($envPy.Trim() -match '^(1|true|yes)$')
    $row = [ordered]@{
        UseExe          = $false
        Path            = $agent
        Reason          = 'python'
        Sha256          = ''
        SourceCommit    = ''
        ProductVersion  = ''
    }
    if (-not $wantPy -and (Test-Path -LiteralPath $earExe -PathType Leaf)) {
        $row.UseExe = $true
        $row.Path = $earExe
        $row.Reason = 'installed-exe'
        try {
            $row.Sha256 = [string](Get-FileHash -LiteralPath $earExe -Algorithm SHA256).Hash
        } catch { }
        # FR #7300: ear source= is the ear component only (CI provenance next to exe).
        # Do not paint install-root MANIFEST.json (Slab saw root 4746581).
        $provCandidates = @(
            (Join-Path $ScriptDir 'provenance.txt'),
            (Join-Path $ScriptDir 'manifest.txt'),
            (Join-Path $ScriptDir 'bob-ear.provenance.txt')
        )
        foreach ($p in $provCandidates) {
            $v = Get-BobEarSourceCommitFromProvenance -Path $p
            if ($v) { $row.SourceCommit = $v; break }
        }
        if (-not $row.SourceCommit) {
            $jsonCandidates = @(
                (Join-Path $ScriptDir 'MANIFEST.json'),
                (Join-Path $ScriptDir 'bob-ear.MANIFEST.json'),
                (Join-Path $ScriptDir 'bob-ear.manifest.json')
            )
            foreach ($man in $jsonCandidates) {
                $v = Get-BobEarSourceCommitFromJson -Path $man
                if ($v) { $row.SourceCommit = $v; break }
            }
        }
        $verFile = Join-Path $InstallRoot 'VERSION'
        if (Test-Path -LiteralPath $verFile -PathType Leaf) {
            try {
                $row.ProductVersion = ((Get-Content -LiteralPath $verFile -TotalCount 1) -as [string]).Trim()
            } catch { }
        }
    } elseif ($wantPy) {
        $row.Reason = 'BOB_EAR_PYTHON'
    } else {
        $row.Reason = 'no-exe'
    }
    return [pscustomobject]$row
}
