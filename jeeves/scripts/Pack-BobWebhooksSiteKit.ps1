#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9776: write the webhooks site-kit artifact (MANIFEST.json + www). No MSI, no Ergo.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [Parameter(Mandatory)]
    [string]$OutDir
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$py = Join-Path $RepoRoot 'jeeves\scripts\jeeves_webhooks_ci.py'
if (-not (Test-Path -LiteralPath $py)) { throw "missing $py" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$published = Join-Path $OutDir 'published'
python $py --repo-root $RepoRoot --physical $published --out $OutDir --commit HEAD
if ($LASTEXITCODE -ne 0) { throw "jeeves_webhooks_ci.py exit $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath (Join-Path $OutDir 'MANIFEST.json'))) { throw 'missing MANIFEST.json' }
Get-ChildItem -LiteralPath $OutDir -Recurse -File | ForEach-Object {
    if ($_.Name -like 'jeeves-*.msi' -or $_.Name -eq 'ergo.exe') {
        throw "webhooks pack must not emit $($_.Name) (FR #9776)"
    }
}
Write-Host "INFO webhooks site kit at $OutDir"
