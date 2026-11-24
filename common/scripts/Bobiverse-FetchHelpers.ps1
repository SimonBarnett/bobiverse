#Requires -Version 5.1
<#
.SYNOPSIS
  Shared download/extract helpers for Fetch-Ergo / Fetch-Wix / Fetch-Nssm (FR #3965).
.NOTES
  WinPS 5.1 Invoke-WebRequest and Expand-Archive paint a progress bar per chunk/file.
  In a hidden or non-interactive host that stalls or never finishes; -TimeoutSec does
  not cover a stalled body read. Prefer curl.exe --max-time and tar.exe / ZipFile.
#>

function Get-BobiverseCurlPath {
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (Test-Path -LiteralPath $curl) { return $curl }
    $cmd = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Get-BobiverseTarPath {
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path -LiteralPath $tar) { return $tar }
    $cmd = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Invoke-BobiverseDownload {
    <#
      Download $Url to $OutFile. curl.exe --max-time first, then IWR with
      ProgressPreference SilentlyContinue + TimeoutSec. Retries once per method.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Url,
        [Parameter(Mandatory)]
        [string]$OutFile,
        [int]$TimeoutSec = 120,
        [string]$UserAgent = 'bobiverse-fetch',
        [int]$Retries = 1
    )
    $prevProgress = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $dir = Split-Path -Parent $OutFile
        if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        $attempts = 1 + [Math]::Max(0, $Retries)
        $lastErr = $null
        for ($i = 1; $i -le $attempts; $i++) {
            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue

            $curl = Get-BobiverseCurlPath
            if ($curl) {
                try {
                    Write-Host ("INFO download-try method=curl attempt={0}/{1} max-time={2}s url={3}" -f $i, $attempts, $TimeoutSec, $Url)
                    $prevEap = $ErrorActionPreference
                    $ErrorActionPreference = 'Continue'
                    $clog = & $curl -sSL --fail --retry 2 --retry-delay 2 --connect-timeout 30 --max-time $TimeoutSec `
                        -A $UserAgent -o $OutFile $Url 2>&1
                    $ccode = $LASTEXITCODE
                    $ErrorActionPreference = $prevEap
                    if ($ccode -eq 0 -and (Test-Path -LiteralPath $OutFile) -and ((Get-Item -LiteralPath $OutFile).Length -gt 0)) {
                        Write-Host ("INFO download-ok method=curl bytes={0}" -f (Get-Item -LiteralPath $OutFile).Length)
                        return
                    }
                    $lastErr = "curl exit=$ccode $(($clog | Select-Object -First 3) -join ' ')"
                    Write-Host "WARN download-warn method=curl $lastErr"
                } catch {
                    $lastErr = "curl $($_.Exception.GetType().Name): $($_.Exception.Message)"
                    Write-Host "WARN download-warn $lastErr"
                }
            } else {
                Write-Host 'WARN download-warn curl.exe not found'
            }

            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            try {
                Write-Host ("INFO download-try method=iwr attempt={0}/{1} timeout={2}s url={3}" -f $i, $attempts, $TimeoutSec, $Url)
                Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec $TimeoutSec `
                    -Headers @{ 'User-Agent' = $UserAgent }
                if ((Test-Path -LiteralPath $OutFile) -and ((Get-Item -LiteralPath $OutFile).Length -gt 0)) {
                    Write-Host ("INFO download-ok method=iwr bytes={0}" -f (Get-Item -LiteralPath $OutFile).Length)
                    return
                }
                $lastErr = 'iwr produced empty file'
                Write-Host "WARN download-warn $lastErr"
            } catch {
                $lastErr = "iwr $($_.Exception.GetType().Name): $($_.Exception.Message)"
                Write-Host "WARN download-warn method=iwr $lastErr"
            }

            if ($i -lt $attempts) { Start-Sleep -Seconds ([Math]::Min(3 * $i, 10)) }
        }
        Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
        throw "download-failed after $attempts attempts: $lastErr (seed third_party cache or set a mirror URL / BOBIVERSE_*_MIRROR)"
    }
    finally {
        $ProgressPreference = $prevProgress
    }
}

function Expand-BobiverseZip {
    <#
      Extract zip without Expand-Archive progress stalls. Prefer tar.exe, else ZipFile.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ZipPath,
        [Parameter(Mandatory)]
        [string]$Destination
    )
    $prevProgress = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        if (-not (Test-Path -LiteralPath $ZipPath)) { throw "zip missing: $ZipPath" }
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        $tar = Get-BobiverseTarPath
        if ($tar) {
            Write-Host "INFO extract-try method=tar dest=$Destination"
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            $tlog = & $tar -xf $ZipPath -C $Destination 2>&1
            $tcode = $LASTEXITCODE
            $ErrorActionPreference = $prevEap
            if ($tcode -eq 0) {
                Write-Host 'INFO extract-ok method=tar'
                return
            }
            Write-Host "WARN extract-warn method=tar exit=$tcode $(($tlog | Select-Object -First 3) -join ' ')"
        }
        Write-Host "INFO extract-try method=zipfile dest=$Destination"
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Destination)
        Write-Host 'INFO extract-ok method=zipfile'
    }
    finally {
        $ProgressPreference = $prevProgress
    }
}

function Ensure-BobiverseFileHashCommand {
    # FR #7355 / MRB #7550 / FIX #7550: GHA/seat shells with PSModuleAutoLoadingPreference=None
    # often leave Get-FileHash missing. Best-effort Import-Module; callers use
    # Get-BobiverseFileSha256 which falls back to System.Security.Cryptography.SHA256.
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) { return }
    $prev = $env:PSModuleAutoLoadingPreference
    try {
        $env:PSModuleAutoLoadingPreference = 'All'
        Import-Module Microsoft.PowerShell.Utility -ErrorAction SilentlyContinue | Out-Null
    } finally {
        if ($null -eq $prev -or $prev -eq '') {
            Remove-Item Env:\PSModuleAutoLoadingPreference -ErrorAction SilentlyContinue
        } else {
            $env:PSModuleAutoLoadingPreference = $prev
        }
    }
}

function Get-BobiverseFileSha256 {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )
    Ensure-BobiverseFileHashCommand
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    # .NET fallback when Utility still does not export Get-FileHash (GHA Autoload=None).
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not [System.IO.File]::Exists($full)) {
        throw "Get-BobiverseFileSha256: missing path=$Path"
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($full)
        try {
            $hash = $sha.ComputeHash($fs)
            return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
        } finally {
            $fs.Dispose()
        }
    } finally {
        $sha.Dispose()
    }
}

function Assert-BobiverseSha256 {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )
    $want = $Expected.Trim().ToLowerInvariant()
    if (-not $want) { throw 'Assert-BobiverseSha256: empty Expected' }
    $got = Get-BobiverseFileSha256 -Path $Path
    if ($got -ne $want) {
        throw "sha256-mismatch path=$Path got=$got want=$want"
    }
    Write-Host "INFO sha256-verified $got"
}

function Read-BobiverseSha256SumFile {
    <#
      Parse a ``*.sha256`` sidecar (``<hex>  filename`` or bare hex). FR #9354.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Read-BobiverseSha256SumFile: missing $Path"
    }
    $raw = [IO.File]::ReadAllText($Path).Trim()
    if (-not $raw) { throw "Read-BobiverseSha256SumFile: empty $Path" }
    if ($raw -match '([A-Fa-f0-9]{64})') {
        return $Matches[1].ToLowerInvariant()
    }
    throw "Read-BobiverseSha256SumFile: no sha256 hex in $Path"
}

function Resolve-BobiverseGhReleaseTag {
    <#
      Resolve a release tag. Empty -Tag uses ``gh release view`` latest. FR #9354.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Repo,
        [string]$Tag = ''
    )
    $tagNorm = ([string]$Tag).Trim()
    if ($tagNorm) { return $tagNorm }
    $json = & gh release view --repo $Repo --json tagName 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Resolve-BobiverseGhReleaseTag: gh release view failed for ${Repo}: $json"
    }
    $doc = $json | ConvertFrom-Json
    $got = [string]$doc.tagName
    if (-not $got) { throw "Resolve-BobiverseGhReleaseTag: empty tagName for $Repo" }
    return $got.Trim()
}

function Save-BobiverseGhReleaseVerifiedExe {
    <#
      Download ``$AssetName`` + ``$AssetName.sha256`` from a GitHub release, verify, copy to
      ``$Destination``. Returns @{ tag; sha256; bytes; repo; asset; url }. FR #9354 / BOB-49.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Repo,
        [Parameter(Mandatory)]
        [string]$AssetName,
        [Parameter(Mandatory)]
        [string]$Destination,
        [string]$Tag = '',
        [string]$CacheDir = '',
        [int]$TimeoutSec = 600,
        [string]$UserAgent = 'bobiverse-pack-vendor'
    )
    $tagNorm = Resolve-BobiverseGhReleaseTag -Repo $Repo -Tag $Tag
    $cache = if ($CacheDir) { $CacheDir } else {
        Join-Path ([IO.Path]::GetTempPath()) ("bobiverse-gh-" + ($Repo -replace '[\\/]', '-') + "-" + $tagNorm)
    }
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    $exeName = [IO.Path]::GetFileName($AssetName)
    if (-not $exeName) { throw 'Save-BobiverseGhReleaseVerifiedExe: empty AssetName' }
    $sumName = $exeName + '.sha256'
    $exeCache = Join-Path $cache $exeName
    $sumCache = Join-Path $cache $sumName
    $base = "https://github.com/$Repo/releases/download/$tagNorm"
    $exeUrl = "$base/$exeName"
    $sumUrl = "$base/$sumName"
    Invoke-BobiverseDownload -Url $sumUrl -OutFile $sumCache -TimeoutSec ([Math]::Min(120, $TimeoutSec)) -UserAgent $UserAgent
    $want = Read-BobiverseSha256SumFile -Path $sumCache
    $needFetch = $true
    if ((Test-Path -LiteralPath $exeCache -PathType Leaf)) {
        try {
            Assert-BobiverseSha256 -Path $exeCache -Expected $want
            $needFetch = $false
            Write-Host ("INFO gh-release cache hit repo={0} tag={1} asset={2}" -f $Repo, $tagNorm, $exeName)
        } catch {
            Remove-Item -LiteralPath $exeCache -Force -ErrorAction SilentlyContinue
            $needFetch = $true
        }
    }
    if ($needFetch) {
        Invoke-BobiverseDownload -Url $exeUrl -OutFile $exeCache -TimeoutSec $TimeoutSec -UserAgent $UserAgent
        Assert-BobiverseSha256 -Path $exeCache -Expected $want
    }
    $destDir = Split-Path -Parent $Destination
    if ($destDir) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    $srcFull = [IO.Path]::GetFullPath($exeCache)
    $dstFull = [IO.Path]::GetFullPath($Destination)
    if ($srcFull -ne $dstFull) {
        Copy-Item -LiteralPath $exeCache -Destination $Destination -Force
    }
    $bytes = [int64](Get-Item -LiteralPath $Destination).Length
    Write-Host ("INFO gh-release staged repo={0} tag={1} asset={2} bytes={3} sha256={4}" -f $Repo, $tagNorm, $exeName, $bytes, $want)
    return @{
        tag      = $tagNorm
        sha256   = $want
        bytes    = $bytes
        repo     = $Repo
        asset    = $exeName
        url      = $exeUrl
        path     = $Destination
    }
}

function Write-BobiverseVendoredExeManifest {
    <#
      Write a small JSON MANIFEST next to a vendored release exe (FR #9354).
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [hashtable]$Info,
        [string]$Fr = '9354',
        [string]$Bob = ''
    )
    $doc = [ordered]@{
        fr           = $Fr
        bob          = $Bob
        repo         = [string]$Info.repo
        tag          = [string]$Info.tag
        asset        = [string]$Info.asset
        sha256       = [string]$Info.sha256
        bytes        = [int64]$Info.bytes
        url          = [string]$Info.url
        path         = [string]$Info.path
        verified_utc = [datetime]::UtcNow.ToString('o')
    }
    $utf8 = New-Object Text.UTF8Encoding $false
    [IO.File]::WriteAllText($Path, (($doc | ConvertTo-Json -Compress) + [Environment]::NewLine), $utf8)
    # Do not return $Path: Stage-Product ends with `return $stage` and any
    # success-stream path concatenates into $Stage (MRB #9358 / FR #6969 heat).
}
