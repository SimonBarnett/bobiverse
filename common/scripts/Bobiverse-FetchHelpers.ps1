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

function Assert-BobiverseSha256 {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )
    $want = $Expected.Trim().ToLowerInvariant()
    if (-not $want) { throw 'Assert-BobiverseSha256: empty Expected' }
    $got = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($got -ne $want) {
        throw "sha256-mismatch path=$Path got=$got want=$want"
    }
    Write-Host "INFO sha256-verified $got"
}
