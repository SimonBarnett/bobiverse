#Requires -Version 5.1
<#
.SYNOPSIS
  Stage + WiX-pack jeeves, bob, and/or airc MSIs for SimonBarnett/bobiverse releases.
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'jeeves', 'bob', 'airc')]
    [string]$Product = 'all',
    [string]$RepoRoot = '',
    [string]$OutDir = '',
    [string]$Version = '',
    [switch]$KeepStage,
    [switch]$SkipMsi
)

$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (-not $Version) {
    $Version = (Get-Content (Join-Path $RepoRoot 'src\VERSION') -Raw).Trim()
}
$msiVersion = $Version
if ($msiVersion -notmatch '^\d+\.\d+\.\d+') { throw "bad VERSION $Version" }

$fetchNssm = Join-Path $RepoRoot 'scripts\Fetch-Nssm.ps1'
$fetchWix = Join-Path $RepoRoot 'scripts\Fetch-Wix.ps1'
$fetchErgo = Join-Path $RepoRoot 'scripts\Fetch-Ergo.ps1'
$null = & $fetchNssm -OutDir (Join-Path $RepoRoot 'third_party\nssm\win64') -CacheDir (Join-Path $RepoRoot 'third_party\nssm')

$products = if ($Product -eq 'all') { @('jeeves', 'bob', 'airc') } else { @($Product) }

function Resolve-WatchAgentHealthSrc {
    foreach ($c in @(
            (Join-Path $RepoRoot 'third_party\Watch-AgentHealth'),
            $env:BOBIVERSE_WATCH_AGENTHEALTH,
            (Join-Path (Split-Path -Parent $RepoRoot) 'agentic_build\tools\Watch-AgentHealth'),
            (Join-Path $env:USERPROFILE 'agentic_build\tools\Watch-AgentHealth'),
            'C:\Users\Administrator\agentic_build\tools\Watch-AgentHealth'
        )) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'Watch-AgentHealth.ps1'))) {
            return $c
        }
    }
    return $null
}

function Stage-Product([string]$Name) {
    $stage = Join-Path $OutDir ("$Name-$Version")
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force -Path "$stage\scripts", "$stage\docs", "$stage\.grok\skills", "$stage\src", "$stage\config", "$stage\third_party\nssm\win64" | Out-Null
    Copy-Item (Join-Path $RepoRoot 'scripts\*') (Join-Path $stage 'scripts') -Recurse -Force
    Copy-Item (Join-Path $RepoRoot 'src\VERSION') (Join-Path $stage 'VERSION') -Force
    Copy-Item (Join-Path $RepoRoot 'src\VERSION') (Join-Path $stage 'src\VERSION') -Force
    if (Test-Path (Join-Path $RepoRoot '.grok\skills')) {
        Copy-Item (Join-Path $RepoRoot '.grok\skills\*') (Join-Path $stage '.grok\skills') -Recurse -Force
    }
    Copy-Item (Join-Path $RepoRoot 'third_party\nssm\win64\nssm.exe') (Join-Path $stage 'third_party\nssm\win64\nssm.exe') -Force
    # Ergo PASS for airc (and useful for ears)
    foreach ($c in @(
            (Join-Path $RepoRoot 'config\ergo.password'),
            (Join-Path $env:USERPROFILE '.grok\ergo\connect.password')
        )) {
        if (Test-Path -LiteralPath $c) {
            Copy-Item $c (Join-Path $stage 'config\ergo.password') -Force
            Write-Host "INFO $Name embedded config/ergo.password from $c"
            break
        }
    }
    if ($Name -eq 'airc' -and -not (Test-Path (Join-Path $stage 'config\ergo.password'))) {
        throw 'airc pack requires config/ergo.password or packer ~/.grok/ergo/connect.password'
    }
    if ($Name -eq 'jeeves') {
        $ergoStage = Join-Path $stage 'ergo'
        New-Item -ItemType Directory -Force -Path $ergoStage | Out-Null
        $null = & $fetchErgo -OutDir $ergoStage -CacheDir (Join-Path $RepoRoot 'third_party\ergo')
        if (-not (Test-Path -LiteralPath (Join-Path $ergoStage 'ergo.exe'))) {
            throw 'jeeves pack requires ergo.exe (Fetch-Ergo failed)'
        }
        # Optional operator ircd.yaml (never from git secrets); else Install seeds default.yaml
        foreach ($c in @(
                (Join-Path $RepoRoot 'config\ircd.yaml'),
                $env:BOBIVERSE_IRCD_YAML,
                'C:\ai\ergo\ircd.yaml'
            )) {
            if ($c -and (Test-Path -LiteralPath $c)) {
                Copy-Item -LiteralPath $c -Destination (Join-Path $ergoStage 'ircd.yaml') -Force
                Write-Host "INFO jeeves embedded ergo/ircd.yaml from $c"
                break
            }
        }
        Write-Host "INFO jeeves staged Ergo payload under ergo\"
    }
    if ($Name -eq 'bob') {
        $wahSrc = Resolve-WatchAgentHealthSrc
        if ($wahSrc) {
            $wahDest = Join-Path $stage 'Watch-AgentHealth'
            New-Item -ItemType Directory -Force -Path $wahDest | Out-Null
            Copy-Item -Path (Join-Path $wahSrc '*') -Destination $wahDest -Recurse -Force
            # Drop binary .lnk shortcuts from foreign trees (recreated by Install if needed)
            Get-ChildItem -Path $wahDest -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue |
                Remove-Item -Force -ErrorAction SilentlyContinue
            Write-Host "INFO bob staged Watch-AgentHealth from $wahSrc"
        } else {
            Write-Host 'WARN bob pack: Watch-AgentHealth source missing (Desktop install will skip)'
        }
    }
    return $stage
}

function Build-Msi([string]$Name, [string]$Stage) {
    if ($SkipMsi) {
        Write-Host "INFO SkipMsi stage=$Stage"
        return
    }
    $wixBin = & $fetchWix -CacheDir (Join-Path $RepoRoot 'third_party\wix')
    $candle = Join-Path $wixBin 'candle.exe'
    $light = Join-Path $wixBin 'light.exe'
    $heat = Join-Path $wixBin 'heat.exe'
    $util = Join-Path $wixBin 'WixUtilExtension.dll'
    $wixWork = Join-Path $OutDir ("wix-$Name-$Version")
    if (Test-Path $wixWork) { Remove-Item -Recurse -Force $wixWork }
    New-Item -ItemType Directory -Force -Path $wixWork | Out-Null

    $installDirName = $Name
    $installPath = "C:\ai\$Name"
    $cg = "Bobiverse$($Name)Files"
    $harvested = Join-Path $wixWork 'HarvestedFiles.wxs'
    & $heat dir $Stage -cg $cg -gg -sfrag -srd -sreg -scom -dr INSTALLDIR -var var.StageDir -out $harvested
    if ($LASTEXITCODE -ne 0) { throw "heat failed $LASTEXITCODE" }

    $upgrade = switch ($Name) {
        'jeeves' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC00FEE001' }
        'bob' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC0000B0B1' }
        'airc' { 'B7E3C9A1-4F2D-4E8B-9C11-A1BC00501E01' }
    }
    $installCmd = switch ($Name) {
        'jeeves' { 'Install-Jeeves.cmd' }
        'bob' { 'Install-Bob.cmd' }
        'airc' { 'Install-Airc.cmd' }
    }
    $guidMark = [guid]::NewGuid().ToString().ToUpper()
    $productWxs = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="bobiverse $Name" Language="1033" Version="$msiVersion"
      Manufacturer="SimonBarnett" UpgradeCode="$upgrade">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" Platform="x64" />
    <MajorUpgrade DowngradeErrorMessage="A newer bobiverse $Name is installed." Schedule="afterInstallInitialize" />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
    <Feature Id="MainFeature" Title="bobiverse $Name" Level="1">
      <ComponentGroupRef Id="$cg" />
      <ComponentRef Id="CmpInstallDirMark" />
    </Feature>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="INSTALLDIR" Name="$installDirName" />
    </Directory>
    <SetDirectory Id="INSTALLDIR" Value="$installPath" />
    <Component Id="CmpInstallDirMark" Directory="INSTALLDIR" Guid="$guidMark">
      <CreateFolder />
      <RegistryValue Root="HKLM" Key="Software\SimonBarnett\bobiverse\$Name" Name="InstallDir" Type="string" Value="[INSTALLDIR]" KeyPath="yes" />
    </Component>
    <CustomAction Id="SetInstallCmd" Property="RunInstall" Value="&quot;[INSTALLDIR]scripts\$installCmd&quot;" Execute="immediate" />
    <CustomAction Id="RunInstall" BinaryKey="WixCA" DllEntry="CAQuietExec64" Execute="deferred" Impersonate="no" Return="check" />
    <InstallExecuteSequence>
      <Custom Action="SetInstallCmd" After="InstallFiles">NOT Installed OR REINSTALL</Custom>
      <Custom Action="RunInstall" After="SetInstallCmd">NOT Installed OR REINSTALL</Custom>
    </InstallExecuteSequence>
  </Product>
</Wix>
"@
    $pw = Join-Path $wixWork 'Product.wxs'
    [IO.File]::WriteAllText($pw, $productWxs, [Text.UTF8Encoding]::new($false))

    Push-Location $wixWork
    try {
        & $candle -nologo -ext $util "-dProductVersion=$msiVersion" "-dStageDir=$Stage" Product.wxs HarvestedFiles.wxs
        if ($LASTEXITCODE -ne 0) { throw "candle failed $LASTEXITCODE" }
        $msi = Join-Path $OutDir ("$Name-$Version.msi")
        if (Test-Path $msi) { Remove-Item -Force $msi }
        & $light -nologo -ext $util -cultures:en-us -out $msi Product.wixobj HarvestedFiles.wixobj
        if ($LASTEXITCODE -ne 0) { throw "light failed $LASTEXITCODE" }
        $hash = (Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLower()
        Set-Content -LiteralPath ($msi + '.sha256') -Value ("$hash  $Name-$Version.msi") -Encoding ascii
        Write-Host "INFO packed $msi sha256=$hash"
    } finally {
        Pop-Location
    }
    if (-not $KeepStage) {
        Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $wixWork -ErrorAction SilentlyContinue
    }
}

foreach ($p in $products) {
    $stage = Stage-Product $p
    Build-Msi $p $stage
}

Get-ChildItem $OutDir -Filter *.msi | Format-Table Name, Length -AutoSize
