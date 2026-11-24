# FR #9270 / BOB-TRAY-UI-09: Agents > Jeeves butler icon from bob.ntsa.uk cache
# or jeeves/assets/jeeves-butler.ico offline fallback.

function Get-BobTrayJeevesButlerUrl {
    $envUrl = [string]$env:BOB_JEEVES_BUTLER_URL
    if ($envUrl -and $envUrl.Trim().Length -gt 0) { return $envUrl.Trim() }
    return 'https://bob.ntsa.uk/jeeves/assets/jeeves-butler.ico'
}

function Get-BobTrayJeevesButlerCachePath {
    param([Parameter(Mandatory)][string]$RepoRoot)
    return (Join-Path $RepoRoot 'assets\jeeves-butler.ico')
}

function Get-BobTrayJeevesButlerFallbackPath {
    param([Parameter(Mandatory)][string]$RepoRoot)
    # FR #9587: tray-vendored butler beside plan-gantt, then jeeves/assets.
    $trayAsset = Join-Path $RepoRoot 'bob\tray\assets\jeeves-butler.ico'
    if (Test-Path -LiteralPath $trayAsset) { return $trayAsset }
    $fallback = Join-Path $RepoRoot 'jeeves\assets\jeeves-butler.ico'
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    $parent = Split-Path -Parent $RepoRoot
    if ($parent) {
        $altTray = Join-Path $parent 'bob\tray\assets\jeeves-butler.ico'
        if (Test-Path -LiteralPath $altTray) { return $altTray }
        $alt = Join-Path $parent 'jeeves\assets\jeeves-butler.ico'
        if (Test-Path -LiteralPath $alt) { return $alt }
    }
    $flat = Join-Path $RepoRoot 'assets\jeeves-butler.ico'
    if (Test-Path -LiteralPath $flat) { return $flat }
    return $fallback
}

function Test-BobTrayIcoMagic {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            $buf = New-Object byte[] 4
            if ($fs.Read($buf, 0, 4) -lt 4) { return $false }
            return ($buf[0] -eq 0 -and $buf[1] -eq 0 -and $buf[2] -eq 1 -and $buf[3] -eq 0)
        } finally { $fs.Dispose() }
    } catch { return $false }
}

function Save-BobTrayJeevesButlerCache {
    param(
        [Parameter(Mandatory)][string]$CachePath,
        [Parameter(Mandatory)][string]$Url,
        [int]$TimeoutMs = 3000
    )
    $dir = Split-Path -Parent $CachePath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $req = [System.Net.HttpWebRequest]::Create($Url)
    $req.Method = 'GET'
    $req.Timeout = $TimeoutMs
    $req.ReadWriteTimeout = $TimeoutMs
    $resp = $null
    try {
        $resp = $req.GetResponse()
        $ms = New-Object System.IO.MemoryStream
        $stream = $resp.GetResponseStream()
        $buf = New-Object byte[] 8192
        while (($n = $stream.Read($buf, 0, $buf.Length)) -gt 0) {
            $ms.Write($buf, 0, $n)
        }
        $bytes = $ms.ToArray()
        if ($bytes.Length -lt 4) { return $false }
        if (-not ($bytes[0] -eq 0 -and $bytes[1] -eq 0 -and $bytes[2] -eq 1 -and $bytes[3] -eq 0)) {
            return $false
        }
        $tmp = $CachePath + '.tmp'
        [System.IO.File]::WriteAllBytes($tmp, $bytes)
        Move-Item -LiteralPath $tmp -Destination $CachePath -Force
        return $true
    } catch {
        return $false
    } finally {
        if ($resp) { $resp.Close() }
    }
}

function Resolve-BobTrayJeevesButlerIcon {
    <#
      FR #9270 / BOB-TRAY-UI-09:
      Prefer <install>\assets\jeeves-butler.ico (filled from bob.ntsa.uk on first online load).
      Offline fallback: jeeves\assets\jeeves-butler.ico beside the install/repo root.
      -SkipFetch / BOB_JEEVES_BUTLER_SKIP_FETCH=1 skips the network (tests).
    #>
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [switch]$SkipFetch
    )
    $cache = Get-BobTrayJeevesButlerCachePath -RepoRoot $RepoRoot
    $fallback = Get-BobTrayJeevesButlerFallbackPath -RepoRoot $RepoRoot
    if (Test-BobTrayIcoMagic -Path $cache) { return $cache }

    $skip = $SkipFetch -or ([string]$env:BOB_JEEVES_BUTLER_SKIP_FETCH -eq '1')
    if (-not $skip) {
        $url = Get-BobTrayJeevesButlerUrl
        if (Save-BobTrayJeevesButlerCache -CachePath $cache -Url $url) {
            if (Test-BobTrayIcoMagic -Path $cache) { return $cache }
        }
    }
    if (Test-BobTrayIcoMagic -Path $fallback) { return $fallback }
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}
