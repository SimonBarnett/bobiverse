#Requires -Version 5.1
<#
.SYNOPSIS
  FR #7233: pick bob-ear.exe vs python irc_agent.py without comparing file mtimes.
.NOTES
  Installed bob-ear.exe always wins when present. Python only when the exe is
  missing or BOB_EAR_PYTHON is 1/true/yes (dev/hotpatch fallback). Logs SHA-256
  plus MANIFEST source_commit and VERSION when those files exist.
#>

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
        $man = Join-Path $InstallRoot 'MANIFEST.json'
        if (Test-Path -LiteralPath $man -PathType Leaf) {
            try {
                $j = Get-Content -LiteralPath $man -Raw -Encoding UTF8 | ConvertFrom-Json
                foreach ($k in @('source_commit', 'workflow_commit', 'commit')) {
                    $v = [string]$j.$k
                    if ($v.Trim()) { $row.SourceCommit = $v.Trim(); break }
                }
            } catch { }
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
