#Requires -Version 5.1
<#
.SYNOPSIS
  Fail-closed check that a bobiverse GitHub release has MSI (+ sha256) assets for each fleet product.

.DESCRIPTION
  FR #2354: v0.1.22 shipped only bob-*.msi; airc self-update Check returned no-matching-asset.
  UAT / release publish must run Pack-BobiverseRelease -Product all and upload every product MSI.

.EXAMPLE
  .\Assert-BobiverseReleaseAssets.ps1 -Repo SimonBarnett/bobiverse -Tag v0.1.22
#>
[CmdletBinding()]
param(
    [string]$Repo = 'SimonBarnett/bobiverse',
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string[]]$Products = @('bob', 'airc', 'jeeves'),
    [switch]$AllowMissing
)

$ErrorActionPreference = 'Stop'
if ($Tag -notmatch '^v?\d+\.\d+\.\d+') { throw "bad Tag $Tag (want vX.Y.Z)" }
$ver = $Tag.TrimStart('v')
$tagNorm = if ($Tag.StartsWith('v')) { $Tag } else { "v$Tag" }

$json = gh release view $tagNorm --repo $Repo --json assets,tagName 2>&1
if ($LASTEXITCODE -ne 0) { throw "gh release view failed: $json" }
$rel = $json | ConvertFrom-Json
$names = @($rel.assets | ForEach-Object { $_.name })

$missing = New-Object System.Collections.Generic.List[string]
foreach ($p in $Products) {
    $msi = "$p-$ver.msi"
    $sum = "$p-$ver.msi.sha256"
    if ($names -notcontains $msi) { [void]$missing.Add($msi) }
    if ($names -notcontains $sum) { [void]$missing.Add($sum) }
}

$result = [ordered]@{
    ok           = ($missing.Count -eq 0)
    repo         = $Repo
    tag          = $tagNorm
    version      = $ver
    assets       = $names
    missing      = @($missing)
    products     = $Products
}

if (-not $result.ok) {
    $msg = "release $tagNorm missing assets: $($missing -join ', ')"
    if ($AllowMissing) {
        Write-Warning $msg
        $result | ConvertTo-Json -Compress
        exit 2
    }
    Write-Error $msg
    $result | ConvertTo-Json -Compress
    exit 1
}

Write-Host "OK release $tagNorm has MSI+sha256 for: $($Products -join ', ')"
$result | ConvertTo-Json -Compress
exit 0