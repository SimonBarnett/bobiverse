#Requires -Version 5.1
<#
.SYNOPSIS
  FR #9778: build the webhooks site kit, then Pack-BobiverseRelease with -WebhooksArtifactDir.
#>
[CmdletBinding()]
param(
    [string]$Product = 'all',
    [string]$RepoRoot = '',
    [Parameter(Mandatory)]
    [string]$OutDir,
    [Parameter(Mandatory)]
    [string]$Version
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$kit = Join-Path $OutDir 'webhooks-artifact'
$published = Join-Path $OutDir 'webhooks-published'
python (Join-Path $RepoRoot 'jeeves\scripts\jeeves_webhooks_ci.py') --repo-root $RepoRoot --physical $published --out $kit --commit HEAD
if ($LASTEXITCODE -ne 0) { throw "jeeves_webhooks_ci.py exit $LASTEXITCODE" }
& (Join-Path $PSScriptRoot 'Pack-BobiverseRelease.ps1') -Product $Product -RepoRoot $RepoRoot -OutDir $OutDir -Version $Version -WebhooksArtifactDir $kit
if ($LASTEXITCODE -ne 0) { throw "Pack-BobiverseRelease.ps1 exit $LASTEXITCODE" }
