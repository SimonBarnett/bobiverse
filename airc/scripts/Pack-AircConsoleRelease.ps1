#Requires -Version 5.1
<#
.SYNOPSIS
  Build installable release MSI for airc console (FR #253 / issue #305).
.NOTES
  Stages the tree (scripts, bundled NSSM, config/ergo.password), then builds a
  single per-machine .msi via WiX 3 (heat/candle/light). Zip is an internal
  stage only — published artifact is the MSI.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$OutDir = '',
    [string]$Version = '',
    [switch]$KeepStage
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    if ($PSScriptRoot) {
        $RepoRoot = Split-Path -Parent $PSScriptRoot
    } else {
        $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $verFile = Join-Path $RepoRoot 'src\airc_console\VERSION'
    if (Test-Path -LiteralPath $verFile) {
        $Version = (Get-Content $verFile -Raw).Trim()
    } else {
        $Version = '0.1.0'
    }
}

# MSI Product/@Version is major.minor.build (third segment = patch).
$msiVersion = $Version
if ($msiVersion -notmatch '^\d+\.\d+\.\d+') {
    if ($msiVersion -match '^\d+\.\d+$') { $msiVersion = "$msiVersion.0" }
    else { throw "VERSION '$Version' is not major.minor.patch for MSI" }
}

$stage = Join-Path $OutDir ("airc-console-$Version")
if (Test-Path -LiteralPath $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$files = @(
    'scripts\airc_console.py',
    'scripts\airc_console_service.py',
    'scripts\account_map.py',
    'scripts\Start-AircConsole.ps1',
    'scripts\Start-AircConsole.cmd',
    'scripts\Install-AircConsole.ps1',
    'scripts\Install-AircConsole.cmd',
    'scripts\Resolve-AircConsoleNssm.ps1',
    'scripts\Resolve-AircConsolePython.ps1',
    'scripts\Fetch-Nssm.ps1',
    'docs\airc-console-fr253.md',
    'src\airc_console\VERSION',
    'src\airc_console\README.md'
)
foreach ($rel in $files) {
    $src = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $src)) { throw "missing $rel" }
    $dest = Join-Path $stage $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest -Force
}

# Issue #266: ship win64 nssm.exe so clients need not have C:\ai\ergo\nssm.exe.
$nssmStage = Join-Path $stage 'third_party\nssm\win64'
$fetch = Join-Path $RepoRoot 'scripts\Fetch-Nssm.ps1'
& $fetch -OutDir $nssmStage -CacheDir (Join-Path $RepoRoot 'third_party\nssm')
if (-not (Test-Path -LiteralPath (Join-Path $nssmStage 'nssm.exe'))) {
    throw 'pack missing third_party\nssm\win64\nssm.exe after Fetch-Nssm'
}
$readmeNssm = Join-Path $stage 'third_party\nssm\README.txt'
if (-not (Test-Path -LiteralPath $readmeNssm)) {
    Set-Content -LiteralPath $readmeNssm -Encoding ascii -Value @(
        'NSSM (Non-Sucking Service Manager) 2.24 win64',
        'https://nssm.cc/release/nssm-2.24.zip — public domain',
        'Bundled so Install-AircConsole.ps1 works without C:\ai\ergo\nssm.exe (issue #266).'
    )
}

# Issue #294: embed Ergo server PASS. Target clients have no ~/.grok.
$configStage = Join-Path $stage 'config'
New-Item -ItemType Directory -Force -Path $configStage | Out-Null
$readmeCfg = Join-Path $RepoRoot 'config\README.txt'
if (Test-Path -LiteralPath $readmeCfg) {
    Copy-Item -LiteralPath $readmeCfg -Destination (Join-Path $configStage 'README.txt') -Force
}
$ergoSecret = $null
$ergoSource = $null
foreach ($key in @('AIRC_PACK_ERGO_PASSWORD', 'AGENTIC_IRC_PASSWORD', 'AIRC_CONSOLE_SERVER_PASSWORD')) {
    $v = [Environment]::GetEnvironmentVariable($key)
    if ($v -and $v.Trim()) { $ergoSecret = $v.Trim(); $ergoSource = "env:$key"; break }
}
if (-not $ergoSecret) {
    $packerConnect = Join-Path $env:USERPROFILE '.grok\ergo\connect.password'
    if (Test-Path -LiteralPath $packerConnect) {
        $ergoSecret = (Get-Content -LiteralPath $packerConnect -Raw).Trim()
        $ergoSource = $packerConnect
    }
}
if (-not $ergoSecret) {
    $localCfg = Join-Path $RepoRoot 'config\ergo.password'
    if (Test-Path -LiteralPath $localCfg) {
        $ergoSecret = (Get-Content -LiteralPath $localCfg -Raw).Trim()
        $ergoSource = $localCfg
    }
}
if (-not $ergoSecret) {
    throw 'Pack requires Ergo server PASS for config/ergo.password (issue #294): set AIRC_PACK_ERGO_PASSWORD / AGENTIC_IRC_PASSWORD, or pack on a box with ~/.grok/ergo/connect.password'
}
$ergoOut = Join-Path $configStage 'ergo.password'
[IO.File]::WriteAllText($ergoOut, $ergoSecret + "`n", [Text.UTF8Encoding]::new($false))
Write-Host "INFO embedded config/ergo.password from $ergoSource (len=$($ergoSecret.Length); value not printed)"

# Selftest before MSI
$py = (Get-Command python.exe).Source
& $py (Join-Path $stage 'scripts\airc_console_service.py') --selftest
if ($LASTEXITCODE -ne 0) { throw "selftest failed: $LASTEXITCODE" }

# --- WiX MSI (issue #305): single release artifact ---
$fetchWix = Join-Path $RepoRoot 'scripts\Fetch-Wix.ps1'
$wixBin = & $fetchWix -CacheDir (Join-Path $RepoRoot 'third_party\wix')
$candle = Join-Path $wixBin 'candle.exe'
$light = Join-Path $wixBin 'light.exe'
$heat = Join-Path $wixBin 'heat.exe'
foreach ($tool in @($candle, $light, $heat)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "WiX tool missing: $tool" }
}

$wixWork = Join-Path $OutDir ("wix-airc-console-$Version")
if (Test-Path -LiteralPath $wixWork) { Remove-Item -Recurse -Force $wixWork }
New-Item -ItemType Directory -Force -Path $wixWork | Out-Null

$harvested = Join-Path $wixWork 'HarvestedFiles.wxs'
# Harvest stage into ComponentGroup AircConsoleFiles under INSTALLDIR.
& $heat dir $stage `
    -cg AircConsoleFiles `
    -gg -sfrag -srd -sreg -scom `
    -dr INSTALLDIR `
    -var var.StageDir `
    -out $harvested
if ($LASTEXITCODE -ne 0) { throw "heat.exe failed: $LASTEXITCODE" }

$productWxs = Join-Path $RepoRoot 'packaging\airc-console\Product.wxs'
if (-not (Test-Path -LiteralPath $productWxs)) { throw "missing $productWxs" }
Copy-Item -LiteralPath $productWxs -Destination (Join-Path $wixWork 'Product.wxs') -Force

Push-Location $wixWork
try {
    $utilExt = Join-Path $wixBin 'WixUtilExtension.dll'
    if (-not (Test-Path -LiteralPath $utilExt)) {
        throw "WixUtilExtension.dll missing under $wixBin (needed for CAQuietExec64)"
    }
    & $candle -nologo -ext $utilExt `
        "-dProductVersion=$msiVersion" `
        "-dStageDir=$stage" `
        Product.wxs HarvestedFiles.wxs
    if ($LASTEXITCODE -ne 0) { throw "candle.exe failed: $LASTEXITCODE" }

    $msi = Join-Path $OutDir ("airc-console-$Version.msi")
    if (Test-Path -LiteralPath $msi) { Remove-Item -Force $msi }
    & $light -nologo -ext $utilExt `
        -cultures:en-us `
        -out $msi `
        Product.wixobj HarvestedFiles.wixobj
    if ($LASTEXITCODE -ne 0) { throw "light.exe failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $msi)) { throw "MSI not produced: $msi" }
$hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLower()
Set-Content -LiteralPath ($msi + '.sha256') -Value ("$hash  airc-console-$Version.msi") -Encoding ascii
Write-Host "INFO packed $msi"
Write-Host "INFO sha256 $hash"

# Optional: keep stage for debugging; default remove to avoid shipping zip by accident.
if (-not $KeepStage) {
    Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $wixWork -ErrorAction SilentlyContinue
}

Get-Item $msi, ($msi + '.sha256') | Format-Table Name, Length -AutoSize
