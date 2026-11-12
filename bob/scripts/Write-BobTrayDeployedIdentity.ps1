#Requires -Version 5.1
<#
.SYNOPSIS
  FR #6924: write install-root MANIFEST.json + provenance.txt for the tray version label.
.DESCRIPTION
  Keeps MSI VERSION / ARP unchanged. Callers (Sync, Build-BobDialogs, Pack, CI, Slab
  hotpatch) pass the source commit being deployed so About/Status/TipForm can show
  ``bob <MSI> (<shortsha>)``. Prefer MANIFEST.json (same shape as Jeeves/worker);
  also write provenance.txt (workflow_commit=) for FR #6285 artifact parity.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$Commit,
    [string]$Product = 'bob',
    [string]$Builder = 'Write-BobTrayDeployedIdentity.ps1',
    [string]$Fr = '6924'
)
$ErrorActionPreference = 'Stop'
$sha = ([string]$Commit).Trim()
if (-not $sha) { throw 'Write-BobTrayDeployedIdentity: Commit is empty' }
if ($sha -notmatch '^[0-9a-fA-F]{7,40}$') {
    throw ("Write-BobTrayDeployedIdentity: Commit is not a hex SHA: {0}" -f $sha)
}
$root = [IO.Path]::GetFullPath($InstallRoot.TrimEnd('\', '/'))
if (-not (Test-Path -LiteralPath $root)) {
    New-Item -ItemType Directory -Force -Path $root | Out-Null
}
$short = $sha.ToLowerInvariant().Substring(0, [Math]::Min(7, $sha.Length))
$utc = [datetime]::UtcNow.ToString('o')
$manifest = [ordered]@{
    product         = $Product
    source_commit   = $sha.ToLowerInvariant()
    workflow_commit = $sha.ToLowerInvariant()
    short_sha       = $short
    built_utc       = $utc
    builder         = $Builder
    fr              = $Fr
}
$utf8 = New-Object Text.UTF8Encoding $false
$manPath = Join-Path $root 'MANIFEST.json'
[IO.File]::WriteAllText($manPath, (($manifest | ConvertTo-Json -Compress) + [Environment]::NewLine), $utf8)

$provLines = @(
    "source_commit=$($sha.ToLowerInvariant())"
    "workflow_commit=$($sha.ToLowerInvariant())"
    "builder=$Builder"
    "fr=$Fr"
    "built_utc=$utc"
)
$provText = ($provLines -join [Environment]::NewLine) + [Environment]::NewLine
$provPath = Join-Path $root 'provenance.txt'
[IO.File]::WriteAllText($provPath, $provText, $utf8)
$tools = Join-Path $root 'tools'
if (Test-Path -LiteralPath $tools) {
    [IO.File]::WriteAllText((Join-Path $tools 'provenance.txt'), $provText, $utf8)
}
Write-Host ("INFO tray-deployed-identity root={0} short={1} manifest={2}" -f $root, $short, $manPath)
return $manPath
