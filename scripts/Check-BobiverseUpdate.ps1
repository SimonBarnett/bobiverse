#Requires -Version 5.1
<#
.SYNOPSIS
  If a newer GitHub Release MSI exists for this product, download and clean-install it.
.PARAMETER Product
  jeeves | bob | airc — selects asset prefix and install tree.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('jeeves', 'bob', 'airc')]
    [string]$Product,
    [string]$Repo = 'SimonBarnett/bobiverse',
    [string]$InstallRoot = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
if ($env:BOBIVERSE_NO_UPDATE -eq '1') {
    Write-Host 'INFO update-skip BOBIVERSE_NO_UPDATE=1'
    exit 0
}

if (-not $InstallRoot) {
    $InstallRoot = Join-Path 'C:\ai' $Product
}
$verFile = Join-Path $InstallRoot 'VERSION'
$local = '0.0.0'
if (Test-Path -LiteralPath $verFile) {
    $local = (Get-Content -LiteralPath $verFile -Raw).Trim()
}

$prefix = switch ($Product) {
    'jeeves' { 'jeeves-' }
    'bob' { 'bob-' }
    'airc' { 'airc-' }
}

# Prefer gh; fall back to API
$tag = $null
$msiName = $null
$msiUrl = $null
$shaUrl = $null
try {
    $relJson = gh api "repos/$Repo/releases/latest" 2>$null
    if ($relJson) {
        $rel = $relJson | ConvertFrom-Json
        foreach ($a in @($rel.assets)) {
            if ($a.name -like "$prefix*.msi" -and $a.name -notlike '*.sha256') {
                $msiName = $a.name
                $msiUrl = $a.browser_download_url
            }
            if ($a.name -like "$prefix*.msi.sha256") {
                $shaUrl = $a.browser_download_url
            }
        }
        if ($msiName -match "$prefix(\d+\.\d+\.\d+)") { $tag = $Matches[1] }
        elseif ($rel.tag_name -match '(\d+\.\d+\.\d+)') { $tag = $Matches[1] }
    }
} catch {
    Write-Host "INFO update-skip gh/api: $($_.Exception.Message)"
    exit 0
}

if (-not $msiUrl -or -not $tag) {
    Write-Host 'INFO update-skip no matching release asset'
    exit 0
}

function ConvertTo-Version([string]$s) {
    try { return [version]$s } catch { return [version]'0.0.0' }
}
if ((ConvertTo-Version $tag) -le (ConvertTo-Version $local)) {
    Write-Host "INFO update-skip local=$local remote=$tag"
    exit 0
}

Write-Host "INFO update-available local=$local remote=$tag asset=$msiName"
if ($DryRun) { exit 0 }

$tmp = Join-Path $env:TEMP ("bobiverse-update-" + [guid]::NewGuid().ToString('n'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$msiPath = Join-Path $tmp $msiName
Invoke-WebRequest -Uri $msiUrl -OutFile $msiPath -UseBasicParsing
if ($shaUrl) {
    $shaPath = Join-Path $tmp ($msiName + '.sha256')
    Invoke-WebRequest -Uri $shaUrl -OutFile $shaPath -UseBasicParsing
    $want = ((Get-Content $shaPath -Raw) -split '\s+')[0].Trim().ToLower()
    $got = (Get-FileHash -LiteralPath $msiPath -Algorithm SHA256).Hash.ToLower()
    if ($want -ne $got) { throw "sha256 mismatch for $msiName" }
}

Write-Host "INFO update-install $msiPath"
Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $msiPath, '/qn', '/norestart') -Wait -PassThru | Out-Null
Write-Host 'INFO update-install done'
exit 0
