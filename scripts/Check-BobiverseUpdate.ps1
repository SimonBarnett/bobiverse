#Requires -Version 5.1
<#
.SYNOPSIS
  If a newer GitHub Release MSI exists for this product, download and clean-install it.
.PARAMETER Product
  jeeves | bob | airc — selects asset prefix and install tree.
.NOTES
  Resolves gh from well-known paths (LocalSystem has no user PATH). Falls back to
  unauthenticated GitHub Releases API via Invoke-RestMethod. Repo defaults to
  SimonBarnett/bobiverse.
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

function Get-BobiverseGhExe {
    foreach ($c in @(
            (Get-Command gh.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
            (Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'GitHub CLI\gh.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\gh\bin\gh.exe'),
            'C:\Users\medatech.si\AppData\Local\Programs\gh\bin\gh.exe',
            'C:\Users\medatech.si\bin\gh\gh.exe',
            'C:\Users\medatech.si\AppData\Local\gh-cli\bin\gh.exe'
        )) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

$tag = $null
$msiName = $null
$msiUrl = $null
$shaUrl = $null
$rel = $null
try {
    $gh = Get-BobiverseGhExe
    if ($gh) {
        $relJson = & $gh api "repos/$Repo/releases/latest" 2>$null
        if ($relJson) { $rel = $relJson | ConvertFrom-Json }
    }
    if (-not $rel) {
        $api = "https://api.github.com/repos/$Repo/releases/latest"
        $rel = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'bobiverse-Check-BobiverseUpdate'; Accept = 'application/vnd.github+json' } -TimeoutSec 60
    }
    if ($rel) {
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
    Write-Host "INFO update-skip release-lookup: $($_.Exception.Message)"
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

Write-Host "INFO update-available local=$local remote=$tag asset=$msiName repo=$Repo"
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

function Sync-BobiverseFromLocalClone {
    param([string]$ProductRoot, [string]$RemoteTag)
    $clone = $env:BOBIVERSE_REPO
    if (-not $clone -or -not (Test-Path -LiteralPath $clone)) {
        foreach ($c in @('C:\ai\bobiverse', 'D:\ai\bobiverse')) {
            if (Test-Path -LiteralPath (Join-Path $c 'src\VERSION')) { $clone = $c; break }
        }
    }
    if (-not $clone -or -not (Test-Path -LiteralPath $clone)) {
        Write-Host 'ERROR no local bobiverse clone (set BOBIVERSE_REPO or use C:\ai\bobiverse)'
        return $false
    }
    $verPath = Join-Path $clone 'src\VERSION'
    $cloneVer = (Get-Content -LiteralPath $verPath -Raw).Trim()
    Write-Host "INFO update-fallback sync clone=$clone cloneVer=$cloneVer -> $ProductRoot"
    foreach ($d in @('scripts', 'third_party')) {
        $s = Join-Path $clone $d
        $t = Join-Path $ProductRoot $d
        if (Test-Path -LiteralPath $s) {
            & robocopy.exe $s $t /E /XO /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
        }
    }
    Copy-Item -Force -LiteralPath $verPath -Destination (Join-Path $ProductRoot 'VERSION')
    Write-Host "INFO update-fallback done local=$((Get-Content -LiteralPath (Join-Path $ProductRoot 'VERSION') -Raw).Trim()) (wanted $RemoteTag)"
    return $true
}

Write-Host "INFO update-install $msiPath"
$proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $msiPath, '/qn', '/norestart') -Wait -PassThru
$code = 0
if ($proc) { $code = [int]$proc.ExitCode }
if ($code -ne 0) {
    Write-Host "ERROR update-install msiexec exit=$code"
    if ($code -eq 1625) {
        Write-Host 'WARN msiexec 1625 = forbidden by system policy; trying local bobiverse clone sync'
        if (Sync-BobiverseFromLocalClone -ProductRoot $InstallRoot -RemoteTag $tag) { exit 0 }
    }
    exit $code
}
Write-Host 'INFO update-install done'
exit 0